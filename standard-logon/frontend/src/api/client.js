import axios from 'axios'

// Every call goes to /api/..., which Vite forwards to Django while developing
// and Nginx forwards on a real server. The same code runs in both places.
export default axios.create({ baseURL: '/api' })
