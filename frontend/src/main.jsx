import React from 'react';
import ReactDOM from 'react-dom/client';
import { CssBaseline, ThemeProvider, createTheme } from '@mui/material';
import App from './App.jsx';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#3157a4' },
    background: { default: '#f4f6fa', paper: '#ffffff' },
    text: { primary: '#182230', secondary: '#667085' },
  },
  shape: { borderRadius: 12 },
  typography: {
    fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    h4: { fontWeight: 700, letterSpacing: '-0.035em' },
    h6: { fontWeight: 650, letterSpacing: '-0.02em' },
    button: { textTransform: 'none', fontWeight: 600 },
  },
});

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </React.StrictMode>,
);
