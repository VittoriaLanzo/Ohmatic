module.exports = {
  apps: [{
    name: "ohmatic-frontend",
    script: "node_modules/vite/bin/vite.js",
    cwd: __dirname,
    args: "--port 5173",
    watch: false,
    autorestart: true,
    max_restarts: 100,
    restart_delay: 2000,
    min_uptime: "5s",
    env: {
      VITE_OHMATIC_USE_MOCK: "1"
    }
  }]
};
