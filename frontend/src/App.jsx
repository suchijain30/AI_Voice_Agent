import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  AppBar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Divider,
  Paper,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Toolbar,
  Typography,
} from '@mui/material';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const EMPTY_FORM = {
  full_name: '', phone_number: '', email: '', job_title: '', job_description: '',
  years_of_experience: '', skills: '', location: '',
};

function errorMessage(error) {
  if (!error || typeof error !== 'object') return 'Something went wrong. Please try again.';
  if (Array.isArray(error.detail)) {
    return error.detail.map((item) => `${item.loc?.at(-1) || 'Field'}: ${item.msg}`).join(' ');
  }
  return error.detail || error.message || 'Something went wrong. Please try again.';
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
    });
  } catch {
    throw new Error(`Cannot reach the API at ${API_BASE_URL}. Check that the backend is running.`);
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(errorMessage(body));
  return body;
}

function App() {
  const [form, setForm] = useState(EMPTY_FORM);
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState('');
  const [notice, setNotice] = useState({ open: false, severity: 'success', message: '' });
  const [errors, setErrors] = useState({});

  const refreshCandidates = useCallback(async () => {
    setListLoading(true);
    setListError('');
    try {
      setCandidates(await request('/api/candidates?limit=50&offset=0'));
    } catch (error) {
      setListError(error.message);
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => { refreshCandidates(); }, [refreshCandidates]);

  const candidateCount = useMemo(() => candidates.length, [candidates]);

  function updateField(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
    setErrors((current) => ({ ...current, [name]: '' }));
  }

  function validate() {
    const next = {};
    ['full_name', 'phone_number', 'job_title', 'job_description'].forEach((key) => {
      if (!form[key].trim()) next[key] = 'This field is required.';
    });
    if (form.phone_number.trim()) {
      const digits = form.phone_number.replace(/\D/g, '').length;
      if (!/^\+?[0-9][0-9 ().-]{5,24}$/.test(form.phone_number.trim()) || digits < 7 || digits > 15) {
        next.phone_number = 'Enter a valid phone number with 7 to 15 digits.';
      }
    }
    if (form.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) {
      next.email = 'Enter a valid email address.';
    }
    if (form.years_of_experience.trim()) {
      const years = Number(form.years_of_experience);
      if (!Number.isFinite(years) || years < 0 || years > 80 || !/^\d{1,2}(\.\d)?$/.test(form.years_of_experience)) {
        next.years_of_experience = 'Enter a number from 0 to 80, up to one decimal place.';
      }
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function submit(event) {
    event.preventDefault();
    if (loading || !validate()) return;
    setLoading(true);
    const payload = {
      ...form,
      email: form.email.trim() || null,
      years_of_experience: form.years_of_experience === '' ? null : Number(form.years_of_experience),
      skills: form.skills.split(',').map((skill) => skill.trim()).filter(Boolean),
      location: form.location.trim() || null,
    };
    try {
      await request('/api/candidates', { method: 'POST', body: JSON.stringify(payload) });
      setForm({ ...EMPTY_FORM });
      setErrors({});
      setNotice({ open: true, severity: 'success', message: 'Candidate saved successfully.' });
      await refreshCandidates();
    } catch (error) {
      setNotice({ open: true, severity: 'error', message: error.message });
    } finally {
      setLoading(false);
    }
  }

  const field = (name, label, options = {}) => (
    <TextField
      fullWidth
      name={name}
      label={label}
      value={form[name]}
      onChange={updateField}
      error={Boolean(errors[name])}
      helperText={errors[name] || options.helperText || ' '}
      required={options.required || false}
      multiline={options.multiline || false}
      minRows={options.minRows || 1}
      type={options.type || 'text'}
      inputProps={options.inputProps}
      placeholder={options.placeholder}
      disabled={loading}
    />
  );

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="static" elevation={0} color="inherit" sx={{ borderBottom: '1px solid #e8ebf1' }}>
        <Toolbar sx={{ maxWidth: 1160, width: '100%', mx: 'auto', px: { xs: 2, sm: 3 } }}>
          <Box sx={{ width: 34, height: 34, borderRadius: 2, bgcolor: 'primary.main', color: 'white', display: 'grid', placeItems: 'center', fontWeight: 800, mr: 1.5 }}>H</Box>
          <Typography variant="subtitle1" fontWeight={700}>Talent Desk</Typography>
          <Chip label="Recruitment POC" size="small" sx={{ ml: 1.5, bgcolor: '#eef2ff', color: '#3157a4', fontWeight: 600 }} />
          <Box sx={{ flex: 1 }} />
          <Typography variant="body2" color="text.secondary" sx={{ display: { xs: 'none', sm: 'block' } }}>Candidate intake</Typography>
        </Toolbar>
      </AppBar>

      <Container maxWidth="md" sx={{ py: { xs: 4, md: 6 } }}>
        <Stack spacing={0.75} sx={{ mb: 3.5 }}>
          <Typography variant="overline" color="primary.main" fontWeight={700} letterSpacing="0.12em">HIRING WORKSPACE</Typography>
          <Typography variant="h4">Add a candidate</Typography>
          <Typography color="text.secondary">Capture candidate and role details to prepare for an initial screening.</Typography>
        </Stack>

        <Paper component="form" onSubmit={submit} elevation={0} sx={{ p: { xs: 2.25, sm: 4 }, border: '1px solid #e7eaf0', boxShadow: '0 8px 28px rgba(16,24,40,0.04)' }}>
          <Stack spacing={3}>
            <Box>
              <Typography variant="h6">Candidate details</Typography>
              <Typography variant="body2" color="text.secondary">Add the candidate’s contact information and current experience.</Typography>
            </Box>
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 2 }}>
              {field('full_name', 'Full name', { required: true, placeholder: 'e.g. Asha Rao' })}
              {field('phone_number', 'Phone number', { required: true, helperText: errors.phone_number || 'Indian numbers may omit +91; include +country code for other countries.' })}
              {field('email', 'Email address', { type: 'email', helperText: errors.email || 'Optional' })}
              {field('years_of_experience', 'Years of experience', { type: 'number', inputProps: { min: 0, max: 80, step: 0.1 }, helperText: errors.years_of_experience || 'Candidate’s actual work experience, not the role requirement.' })}
              {field('skills', 'Skills', { helperText: 'Optional · Separate skills with commas' })}
              {field('location', 'Location', { helperText: 'Optional · Current or preferred location' })}
            </Box>

            <Divider />

            <Box>
              <Typography variant="h6">Role details</Typography>
              <Typography variant="body2" color="text.secondary">Describe the position this candidate is being considered for.</Typography>
            </Box>
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 2 }}>
              {field('job_title', 'Job title', { required: true, placeholder: 'e.g. Backend Engineer' })}
              <Box sx={{ display: { xs: 'none', sm: 'block' } }} />
              <Box sx={{ gridColumn: { xs: 'auto', sm: '1 / -1' } }}>
                {field('job_description', 'Job description', { required: true, multiline: true, minRows: 4, placeholder: 'Key responsibilities, experience, and role context…' })}
              </Box>
            </Box>

            <Stack direction={{ xs: 'column-reverse', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'stretch', sm: 'center' }} spacing={2}>
              <Typography variant="caption" color="text.secondary">Fields marked with * are required.</Typography>
              <Stack direction="row" spacing={1.5} justifyContent="flex-end">
                <Button type="button" color="inherit" disabled={loading} onClick={() => { setForm({ ...EMPTY_FORM }); setErrors({}); }}>Clear form</Button>
                <Button type="submit" variant="contained" disabled={loading} startIcon={loading ? <CircularProgress size={16} color="inherit" /> : null} sx={{ px: 3, py: 1.1 }}>
                  {loading ? 'Saving…' : 'Save candidate'}
                </Button>
              </Stack>
            </Stack>
          </Stack>
        </Paper>

        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mt: 5, mb: 1.75 }}>
          <Box>
            <Typography variant="h6">Recently added</Typography>
            <Typography variant="body2" color="text.secondary">Candidates saved to the local POC database.</Typography>
          </Box>
          <Chip label={`${candidateCount} ${candidateCount === 1 ? 'candidate' : 'candidates'}`} variant="outlined" />
        </Stack>
        <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid #e7eaf0' }}>
          <Table size="small" aria-label="Candidate list">
            <TableHead><TableRow><TableCell>Name</TableCell><TableCell>Role</TableCell><TableCell>Phone</TableCell><TableCell>Location</TableCell></TableRow></TableHead>
            <TableBody>
              {listLoading ? <TableRow><TableCell colSpan={4} align="center"><Stack direction="row" spacing={1.25} justifyContent="center" alignItems="center" sx={{ py: 2 }}><CircularProgress size={22} /><Typography color="text.secondary">Loading candidates…</Typography></Stack></TableCell></TableRow>
                : listError ? <TableRow><TableCell colSpan={4}><Alert severity="error" action={<Button color="inherit" size="small" onClick={refreshCandidates} disabled={listLoading}>Retry</Button>}>{listError}</Alert></TableCell></TableRow>
                  : candidates.length === 0 ? <TableRow><TableCell colSpan={4} align="center"><Typography color="text.secondary" sx={{ py: 2 }}>No candidates yet. Add the first one above.</Typography></TableCell></TableRow>
                    : candidates.map((candidate) => <TableRow key={candidate.id} hover><TableCell>{candidate.full_name}</TableCell><TableCell>{candidate.job_title}</TableCell><TableCell>{candidate.phone_number}</TableCell><TableCell>{candidate.location || '—'}</TableCell></TableRow>)}
            </TableBody>
          </Table>
        </TableContainer>
      </Container>

      <Snackbar open={notice.open} autoHideDuration={6000} onClose={() => setNotice((current) => ({ ...current, open: false }))} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        <Alert onClose={() => setNotice((current) => ({ ...current, open: false }))} severity={notice.severity} variant="filled" sx={{ width: '100%' }}>{notice.message}</Alert>
      </Snackbar>
    </Box>
  );
}

export default App;
