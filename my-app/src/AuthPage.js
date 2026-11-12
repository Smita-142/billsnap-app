import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, Eye, EyeOff, Lock, Mail, ShieldCheck, User } from 'lucide-react';
import { supabase } from './lib/supabase';
import { useApp } from './App';

export default function AuthPage({ defaultSignup = false }) {
  const [isSignup, setIsSignup] = useState(defaultSignup);
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const { setToast, setName, setEmail: setAppEmail } = useApp() || {};

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!supabase) {
      setError('Authentication is not configured. Set REACT_APP_SUPABASE_URL and REACT_APP_SUPABASE_ANON_KEY first.');
      return;
    }

    if (!email || !password) {
      setError('Please provide both email and password.');
      return;
    }

    if (isSignup && !fullName.trim()) {
      setError('Please provide your full name.');
      return;
    }

    setLoading(true);
    try {
      if (isSignup) {
        const { data, error: signUpError } = await supabase.auth.signUp({
          email,
          password,
          options: {
            data: { full_name: fullName.trim() },
          },
        });
        if (signUpError) throw signUpError;
        if (setName) setName(fullName.trim());
        if (setAppEmail) setAppEmail(email);
        if (setToast) setToast('Account created successfully! Welcome to Bill Snap.');
        navigate('/app');
      } else {
        const { data, error: signInError } = await supabase.auth.signInWithPassword({
          email,
          password,
        });
        if (signInError) throw signInError;
        const name = data.user?.user_metadata?.full_name || '';
        if (setName && name) setName(name);
        if (setAppEmail) setAppEmail(data.user?.email || email);
        if (setToast) setToast('Signed in successfully.');
        navigate('/app');
      }
    } catch (err) {
      setError(err.message || 'Authentication failed. Please check your credentials and try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container" style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px',
      background: 'radial-gradient(ellipse at 50% 20%, #1c202d 0%, #0d1017 100%)',
      color: '#ededed'
    }}>
      <div style={{
        width: '100%',
        maxWidth: '420px',
        background: '#151821',
        border: '1px solid rgba(255, 255, 255, 0.08)',
        borderRadius: '16px',
        padding: '32px',
        boxShadow: '0 20px 40px rgba(0,0,0,0.4)'
      }}>
        <div style={{ textAlign: 'center', marginBottom: '28px' }}>
          <Link to="/" style={{ textDecoration: 'none', display: 'inline-block', marginBottom: '16px' }}>
            <span style={{ fontSize: '20px', fontWeight: 800, color: '#fff', letterSpacing: '-0.5px' }}>
              bill<span style={{ color: '#a78bfa' }}>snap</span>
            </span>
          </Link>
          <h1 style={{ fontSize: '22px', fontWeight: 700, margin: '0 0 8px', color: '#f3f4f6' }}>
            {isSignup ? 'Create your account' : 'Sign in to Bill Snap'}
          </h1>
          <p style={{ margin: 0, fontSize: '13px', color: '#9ca3af' }}>
            A clearer view of your spending starts here.
          </p>
        </div>

        {error && (
          <div style={{
            background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.25)',
            borderRadius: '8px',
            padding: '12px 14px',
            color: '#fca5a5',
            fontSize: '12px',
            marginBottom: '20px',
            lineHeight: 1.5
          }}>
            {error}
          </div>
        )}

        {!supabase && (
          <div style={{
            background: 'rgba(245, 158, 11, 0.1)',
            border: '1px solid rgba(245, 158, 11, 0.25)',
            borderRadius: '8px',
            padding: '12px 14px',
            color: '#fcd34d',
            fontSize: '12px',
            marginBottom: '20px',
            lineHeight: 1.5
          }}>
            Authentication is not configured. Set REACT_APP_SUPABASE_URL and REACT_APP_SUPABASE_ANON_KEY to sign in.
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'grid', gap: '16px' }}>
          {isSignup && (
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: '#9ca3af', marginBottom: '6px' }}>
                Full name
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  type="text"
                  placeholder="e.g. Smita Premchand Pandey"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  required={isSignup}
                  style={{
                    width: '100%',
                    boxSizing: 'border-box',
                    height: '42px',
                    padding: '0 12px 0 36px',
                    background: '#1a1e29',
                    border: '1px solid rgba(255, 255, 255, 0.12)',
                    borderRadius: '8px',
                    color: '#fff',
                    fontSize: '13px'
                  }}
                />
                <User size={16} style={{ position: 'absolute', left: '11px', top: '13px', color: '#6b7280' }} />
              </div>
            </div>
          )}

          <div>
            <label style={{ display: 'block', fontSize: '12px', color: '#9ca3af', marginBottom: '6px' }}>
              Email address
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type="email"
                placeholder="name@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                style={{
                  width: '100%',
                  boxSizing: 'border-box',
                  height: '42px',
                  padding: '0 12px 0 36px',
                  background: '#1a1e29',
                  border: '1px solid rgba(255, 255, 255, 0.12)',
                  borderRadius: '8px',
                  color: '#fff',
                  fontSize: '13px'
                }}
              />
              <Mail size={16} style={{ position: 'absolute', left: '11px', top: '13px', color: '#6b7280' }} />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', color: '#9ca3af', marginBottom: '6px' }}>
              Password
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type={showPassword ? 'text' : 'password'}
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
                style={{
                  width: '100%',
                  boxSizing: 'border-box',
                  height: '42px',
                  padding: '0 36px 0 36px',
                  background: '#1a1e29',
                  border: '1px solid rgba(255, 255, 255, 0.12)',
                  borderRadius: '8px',
                  color: '#fff',
                  fontSize: '13px'
                }}
              />
              <Lock size={16} style={{ position: 'absolute', left: '11px', top: '13px', color: '#6b7280' }} />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  position: 'absolute',
                  right: '10px',
                  top: '12px',
                  background: 'none',
                  border: 'none',
                  padding: 0,
                  cursor: 'pointer',
                  color: '#6b7280'
                }}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%',
              height: '42px',
              marginTop: '8px',
              background: '#8b5cf6',
              color: '#fff',
              border: 'none',
              borderRadius: '8px',
              fontSize: '13px',
              fontWeight: 600,
              cursor: loading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              opacity: loading ? 0.7 : 1,
              transition: 'background 0.2s'
            }}
          >
            {loading ? 'Please wait…' : isSignup ? 'Create account' : 'Sign in'}
            {!loading && <ArrowRight size={15} />}
          </button>
        </form>

        <div style={{
          marginTop: '24px',
          paddingTop: '20px',
          borderTop: '1px solid rgba(255, 255, 255, 0.06)',
          textAlign: 'center',
          fontSize: '12px',
          color: '#9ca3af'
        }}>
          {isSignup ? (
            <span>
              Already have an account?{' '}
              <button
                type="button"
                onClick={() => { setIsSignup(false); setError(''); }}
                style={{ background: 'none', border: 'none', color: '#a78bfa', fontWeight: 600, cursor: 'pointer', padding: 0 }}
              >
                Sign in
              </button>
            </span>
          ) : (
            <span>
              Don't have an account?{' '}
              <button
                type="button"
                onClick={() => { setIsSignup(true); setError(''); }}
                style={{ background: 'none', border: 'none', color: '#a78bfa', fontWeight: 600, cursor: 'pointer', padding: 0 }}
              >
                Create one
              </button>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

