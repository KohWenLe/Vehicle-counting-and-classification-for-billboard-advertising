module.exports = {
  devServer: {
    proxy: {
      '^/analyze': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '^/output': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '^/history': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '/test_gpt_analysis': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
    }
  }
}
