// The one list of pages. The main menu is built from the routes that have a
// `label`, so adding a page to the template is one new line here and the menu
// follows. Pages that do not exist yet use StubView, which names the episode
// that will build the real one.
import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '@/views/HomeView.vue'
import HealthView from '@/views/HealthView.vue'
import StubView from '@/views/StubView.vue'

const routes = [
  { path: '/', name: 'home', component: HomeView, meta: { label: 'Home' } },
  {
    path: '/login',
    name: 'login',
    component: StubView,
    meta: { label: 'Log in', title: 'Log in', episode: 'Episode 2: logon (session or JWT)' },
  },
  {
    path: '/register',
    name: 'register',
    component: StubView,
    meta: { label: 'Register', title: 'Register', episode: 'Episode 2: logon (session or JWT)' },
  },
  {
    path: '/account',
    name: 'account',
    component: StubView,
    meta: { label: 'Account', title: 'Your account', episode: 'Episode 2: logon, with two-factor' },
  },
  { path: '/health', name: 'health', component: HealthView, meta: { label: 'Health' } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const menuItems = routes
  .filter((route) => route.meta && route.meta.label)
  .map((route) => ({ name: route.name, path: route.path, label: route.meta.label }))

export default createRouter({
  history: createWebHistory(),
  routes,
})
