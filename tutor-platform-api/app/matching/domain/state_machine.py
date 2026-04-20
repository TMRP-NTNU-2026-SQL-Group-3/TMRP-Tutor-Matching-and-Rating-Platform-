"""
配對狀態機 — 純邏輯，不依賴任何框架或資料庫。
可以單獨用 pytest 測試所有狀態轉換路徑。
"""
from dataclasses import dataclass

from .exceptions import InvalidTransitionError, MatchPermissionDeniedError
from .value_objects import Action, AllowedActor, MatchStatus


@dataclass(frozen=True)
class Transition:
    new_status: MatchStatus | None
    allowed_actor: AllowedActor


TRANSITIONS: dict[tuple[MatchStatus, Action], Transition] = {
    (MatchStatus.PENDING, Action.CANCEL):
        Transition(MatchStatus.CANCELLED, AllowedActor.PARENT),
    (MatchStatus.PENDING, Action.REJECT):
        Transition(MatchStatus.REJECTED, AllowedActor.TUTOR),
    (MatchStatus.PENDING, Action.ACCEPT):
        Transition(None, AllowedActor.TUTOR),
    (MatchStatus.TRIAL, Action.CONFIRM_TRIAL):
        Transition(MatchStatus.ACTIVE, AllowedActor.EITHER),
    (MatchStatus.TRIAL, Action.REJECT_TRIAL):
        Transition(MatchStatus.REJECTED, AllowedActor.EITHER),
    (MatchStatus.ACTIVE, Action.PAUSE):
        Transition(MatchStatus.PAUSED, AllowedActor.EITHER),
    (MatchStatus.ACTIVE, Action.TERMINATE):
        Transition(MatchStatus.TERMINATING, AllowedActor.EITHER),
    (MatchStatus.PAUSED, Action.RESUME):
        Transition(MatchStatus.ACTIVE, AllowedActor.EITHER),
    (MatchStatus.PAUSED, Action.TERMINATE):
        Transition(MatchStatus.TERMINATING, AllowedActor.EITHER),
    (MatchStatus.TERMINATING, Action.AGREE_TERMINATE):
        Transition(MatchStatus.ENDED, AllowedActor.OTHER_PARTY),
    # DISAGREE_TERMINATE reverts to the match's pre-termination status
    # (active or paused). The resolver cannot know which without the stored
    # reason payload, so the transition uses `new_status=None` and the
    # application layer computes the real next status at commit time from
    # `parsed pre-termination status`. Treating this as an explicit revert
    # avoids the misleading TERMINATING→TERMINATING self-transition the
    # table previously encoded.
    (MatchStatus.TERMINATING, Action.DISAGREE_TERMINATE):
        Transition(None, AllowedActor.OTHER_PARTY),
}


def resolve_transition(
    current: MatchStatus,
    action: Action,
    *,
    actor_is_parent: bool,
    actor_is_tutor: bool,
    actor_is_admin: bool,
    actor_user_id: int,
    terminated_by: int | None,
    want_trial: bool,
) -> MatchStatus | None:
    transition = TRANSITIONS.get((current, action))
    if transition is None:
        raise InvalidTransitionError(
            f"無法在「{current.label}」狀態執行「{action.value}」操作"
        )

    _check_permission(
        transition.allowed_actor,
        actor_is_parent=actor_is_parent,
        actor_is_tutor=actor_is_tutor,
        actor_is_admin=actor_is_admin,
        actor_user_id=actor_user_id,
        terminated_by=terminated_by,
    )

    if action == Action.ACCEPT:
        return MatchStatus.TRIAL if want_trial else MatchStatus.ACTIVE

    return transition.new_status


def _check_permission(
    allowed: AllowedActor,
    *,
    actor_is_parent: bool,
    actor_is_tutor: bool,
    actor_is_admin: bool,
    actor_user_id: int,
    terminated_by: int | None,
) -> None:
    if actor_is_admin and allowed != AllowedActor.OTHER_PARTY:
        return

    match allowed:
        case AllowedActor.PARENT:
            if not actor_is_parent:
                raise MatchPermissionDeniedError("只有家長可以執行此操作")
        case AllowedActor.TUTOR:
            if not actor_is_tutor:
                raise MatchPermissionDeniedError("只有老師可以執行此操作")
        case AllowedActor.EITHER:
            if not actor_is_parent and not actor_is_tutor and not actor_is_admin:
                raise MatchPermissionDeniedError("無權操作此配對")
        case AllowedActor.OTHER_PARTY:
            if terminated_by is None:
                raise InvalidTransitionError("無法確認終止：缺少發起終止方資訊")
            if terminated_by == actor_user_id:
                raise MatchPermissionDeniedError("需要由對方確認此操作")
