module.exports = {
  devServer: {
    proxy: {
      '^/analysis-jobs': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
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
      '^/health': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '^/metrics': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '^/diagnostics': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
    }
  }
}
