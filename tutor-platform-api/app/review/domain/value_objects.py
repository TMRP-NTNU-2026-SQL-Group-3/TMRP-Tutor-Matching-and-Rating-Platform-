from enum import Enum


class ReviewType(str, Enum):
    PARENT_TO_TUTOR = "parent_to_tutor"
    TUTOR_TO_PARENT = "tutor_to_parent"
    TUTOR_TO_STUDENT = "tutor_to_student"
