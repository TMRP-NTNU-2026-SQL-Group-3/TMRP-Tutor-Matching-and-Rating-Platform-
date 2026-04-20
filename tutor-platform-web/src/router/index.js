import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { guest: true }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/RegisterView.vue'),
    meta: { guest: true }
  },

  // 家長端
  {
    path: '/parent',
    meta: { requiresAuth: true, role: 'parent' },
    children: [
      { path: '', name: 'ParentDashboard', component: () => import('@/views/parent/DashboardView.vue') },
      { path: 'search', name: 'SearchTutors', component: () => import('@/views/parent/SearchView.vue') },
      { path: 'tutor/:id', name: 'TutorDetail', component: () => import('@/views/parent/TutorDetailView.vue') },
      { path: 'students', name: 'Students', component: () => import('@/views/parent/StudentsView.vue') },
      { path: 'match/:id', name: 'ParentMatchDetail', component: () => import('@/views/parent/MatchDetailView.vue') },
      { path: 'expense', name: 'Expense', component: () => import('@/views/parent/ExpenseView.vue') },
    ]
  },

  // 老師端
  {
    path: '/tutor',
    meta: { requiresAuth: true, role: 'tutor' },
    children: [
      { path: '', name: 'TutorDashboard', component: () => import('@/views/tutor/DashboardView.vue') },
      { path: 'profile', name: 'TutorProfile', component: () => import('@/views/tutor/ProfileView.vue') },
      { path: 'match/:id', name: 'TutorMatchDetail', component: () => import('@/views/tutor/MatchDetailView.vue') },
      { path: 'income', name: 'Income', component: () => import('@/views/tutor/IncomeView.vue') },
    ]
  },

  // 訊息（僅限家長/老師，管理員無訊息功能）
  {
    path: '/messages',
    // `excludeRoles` is belt-and-braces with `roles`: any future drift in role
    // values (e.g. adding a new role to the allow-list by mistake) still
    // won't leak admin into a surface where admin has no business.
    meta: { requiresAuth: true, roles: ['parent', 'tutor'], excludeRoles: ['admin'] },
    children: [
      { path: '', name: 'Conversations', component: () => import('@/views/messages/ConversationListView.vue') },
      { path: ':id', name: 'Chat', component: () => import('@/views/messages/ChatView.vue') },
    ]
  },

  // 管理員
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('@/views/admin/AdminDashboardView.vue'),
    meta: { requiresAuth: true, role: 'admin' }
  },

  // 預設導向
  {
    path: '/',
    redirect: () => roleHome(),
  },
  // Catchall — route already-authenticated users to their role home so we don't
  // bounce them through /login → home (which produces a brief login flash).
  { path: '/:pathMatch(.*)*', redirect: () => roleHome() },
]

function roleHome() {
  const auth = useAuthStore()
  if (!auth.isLoggedIn) return '/login'
  if (auth.role === 'admin') return '/admin'
  if (auth.role === 'tutor') return '/tutor'
  return '/parent'
}

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守衛
// MEDIUM-4: the guard is async so it can await ensureVerified(), which
// confirms with the server (via HttpOnly-cookie-gated /api/auth/me) that
// the role held in localStorage is authentic. Without this, a browser
// extension or XSS primitive can seed localStorage.user with role="admin"
// and render admin layouts before any API call fails.
router.beforeEach(async (to, from, next) => {
  const auth = useAuthStore()

  const requiresAuth = to.matched.some(record => record.meta.requiresAuth)
  const requiredRole = to.matched.find(record => record.meta.role)?.meta.role
  const allowedRoles = to.matched.find(record => record.meta.roles)?.meta.roles
  const excludedRoles = to.matched.find(record => record.meta.excludeRoles)?.meta.excludeRoles

  // Verify the cached user against the server before authorizing any
  // protected route. ensureVerified() is single-flight and caches success
  // for the session, so this is a one-shot round-trip per page load.
  if ((requiresAuth || to.meta.guest) && auth.isLoggedIn && !auth.verified) {
    try {
      await auth.ensureVerified()
    } catch {
      // Server rejected the session — drop any cached user and fall through
      // so the requiresAuth branch below bounces to /login.
    }
  }

  if (requiresAuth && !auth.isLoggedIn) {
    return next('/login')
  }

  if (to.meta.guest && auth.isLoggedIn) {
    const role = auth.role
    if (role === 'admin') return next('/admin')
    if (role === 'tutor') return next('/tutor')
    return next('/parent')
  }

  if (requiredRole && auth.role !== requiredRole) {
    if (auth.role === 'admin') return next('/admin')
    if (auth.role === 'tutor') return next('/tutor')
    return next('/parent')
  }

  if (excludedRoles && excludedRoles.includes(auth.role)) {
    if (auth.role === 'admin') return next('/admin')
    if (auth.role === 'tutor') return next('/tutor')
    return next('/parent')
  }

  if (allowedRoles && !allowedRoles.includes(auth.role)) {
    if (auth.role === 'admin') return next('/admin')
    if (auth.role === 'tutor') return next('/tutor')
    return next('/parent')
  }

  next()
})

export default router
