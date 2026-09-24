import express from 'express';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { createApiMiddleware } from './src/server/api.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = 3000;

// API routes
app.use('/api', createApiMiddleware());

// Static frontend build
const distPath = path.join(__dirname, 'dist');
app.use(express.static(distPath));

// Fallback to index.html for SPA routes
app.get('*', (_req, res) => {
  res.sendFile(path.join(distPath, 'index.html'));
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`[MaxiConecta] Production Server listening on http://0.0.0.0:${PORT}`);
});
