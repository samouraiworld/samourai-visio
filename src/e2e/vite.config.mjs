export default {
  root: '/frontend',
  preview: {
    proxy: {
      '/api': { target: 'http://backend:8000', changeOrigin: true },
    },
  },
}
