import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import AdminApp from './AdminApp';
import './styles.css';

const basePath = (import.meta.env.BASE_URL || '/').replace(/\/+$/, '');
const pathname = window.location.pathname.replace(/\/+$/, '') || '/';
const normalizedPathname = basePath && basePath !== '/' && pathname.startsWith(basePath)
  ? pathname.slice(basePath.length) || '/'
  : pathname;
const isAdminRoute = normalizedPathname === '/admin' || normalizedPathname.startsWith('/admin/');

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>{isAdminRoute ? <AdminApp /> : <App />}</React.StrictMode>,
);
