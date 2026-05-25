/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import express from 'express';
import path from 'path';
import http from 'http';
import https from 'https';
import { createServer as createViteServer } from 'vite';
import dotenv from 'dotenv';

dotenv.config();

const app = express();
const PORT = Number(process.env.PORT || 3000);
const BACKEND_URL = process.env.MARKHUB_BACKEND_URL || 'http://127.0.0.1:8787';

function proxyToBackend(req: express.Request, res: express.Response) {
  const target = new URL(req.originalUrl, BACKEND_URL);
  const client = target.protocol === 'https:' ? https : http;
  const headers = { ...req.headers, host: target.host };

  const proxyReq = client.request(
    {
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port,
      method: req.method,
      path: `${target.pathname}${target.search}`,
      headers,
    },
    (proxyRes) => {
      res.statusCode = proxyRes.statusCode || 502;
      Object.entries(proxyRes.headers).forEach(([key, value]) => {
        if (value !== undefined) res.setHeader(key, value);
      });
      proxyRes.pipe(res);
    }
  );

  proxyReq.on('error', (error) => {
    if (!res.headersSent) {
      res.status(502).json({ error: `Backend proxy failed: ${error.message}` });
    } else {
      res.end();
    }
  });

  req.pipe(proxyReq);
}

app.use('/api', proxyToBackend);
app.use('/jobs', proxyToBackend);

async function startServer() {
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
    console.log('Vite development server middleware loaded.');
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
    console.log('Production static asset streaming configured.');
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Frontend running on: http://localhost:${PORT}`);
    console.log(`Proxying /api and /jobs to: ${BACKEND_URL}`);
  });
}

startServer();
