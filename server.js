const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const PORT = process.env.PORT || 3000;

// Resolve the Python executable path
let pythonPath = 'python';

// Check for local virtual environment (.venv)
const venvPath = path.join(__dirname, '.venv');
if (fs.existsSync(venvPath)) {
    const winPython = path.join(venvPath, 'Scripts', 'python.exe');
    const nixPython = path.join(venvPath, 'bin', 'python');
    if (fs.existsSync(winPython)) {
        pythonPath = winPython;
    } else if (fs.existsSync(nixPython)) {
        pythonPath = nixPython;
    }
}

console.log(`[Server] Starting Flask application on port ${PORT}...`);
console.log(`[Server] Using Python executable: ${pythonPath}`);

// Spawn the Python Flask process
const pythonProcess = spawn(pythonPath, ['app.py'], {
    env: { ...process.env, PORT: PORT.toString(), HOST: '0.0.0.0' },
    stdio: 'inherit' // Inherit stdio to stream input/output/errors directly
});

pythonProcess.on('error', (err) => {
    console.error('[Server] Failed to start Flask process:', err);
    process.exit(1);
});

pythonProcess.on('close', (code) => {
    console.log(`[Server] Flask process exited with code ${code}`);
    process.exit(code || 0);
});

// Ensure the child process is terminated when Node exits
const cleanup = () => {
    console.log('[Server] Shutting down Flask process...');
    pythonProcess.kill('SIGINT');
};

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('exit', cleanup);
