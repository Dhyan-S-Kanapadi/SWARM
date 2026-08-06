"""Generate optional session authentication files for a generated application.

Architect does not currently emit authentication configuration. When that
contract is extended, add a top-level ``auth`` object such as::

    {"required": true, "protected_paths": ["/api/items", "/api/metrics"]}

``scaffold_auth`` accepts that object directly. It is deliberately a no-op when
``required`` is false, so callers can safely invoke it only after inspecting the
architecture or requirements.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from textwrap import dedent
from typing import Any


def scaffold_auth(
    auth_config: bool | Mapping[str, Any] | None,
    api_routes: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, str]:
    """Return optional auth files in the Builder's relative-path mapping format.

    ``auth_config`` may be a boolean or a mapping with ``required``, optional
    ``protected_paths``, and optional ``session_secret_env`` keys. When paths
    are omitted, non-health API route prefixes are protected from ``api_routes``.
    The generated backend requires the Node packages ``bcryptjs`` and
    ``express-session`` in addition to the ``pg`` package used by the API server.
    """

    config = _normalise_auth_config(auth_config, api_routes)
    if not config["required"]:
        return {}

    encoded_config = json.dumps(config, indent=2)
    return {
        "server/auth.js": dedent(_SERVER_AUTH_TEMPLATE).replace("__AUTH_CONFIG__", encoded_config).strip() + "\n",
        "src/Auth.jsx": dedent(_AUTH_COMPONENT_TEMPLATE).strip() + "\n",
        "src/auth.js": dedent(_AUTH_CLIENT_TEMPLATE).strip() + "\n",
        "src/auth.css": dedent(_AUTH_STYLES_TEMPLATE).strip() + "\n",
    }


def _normalise_auth_config(
    auth_config: bool | Mapping[str, Any] | None,
    api_routes: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    if auth_config is None:
        raw_config: Mapping[str, Any] = {"required": False}
    elif isinstance(auth_config, bool):
        raw_config = {"required": auth_config}
    elif isinstance(auth_config, Mapping):
        raw_config = auth_config
    else:
        raise ValueError("auth_config must be a boolean, a dictionary, or None")

    required = raw_config.get("required", False)
    if not isinstance(required, bool):
        raise ValueError("auth_config.required must be a boolean")
    if not required:
        return {"required": False}

    protected_paths = raw_config.get("protected_paths")
    if protected_paths is None:
        protected_paths = _protected_paths_from_routes(api_routes)
    if not isinstance(protected_paths, list) or not all(
        isinstance(path, str) and (path == "/api" or path.startswith("/api/")) for path in protected_paths
    ):
        raise ValueError("auth_config.protected_paths must be a list of /api paths")

    session_secret_env = raw_config.get("session_secret_env", "SESSION_SECRET")
    if not isinstance(session_secret_env, str) or not session_secret_env.isidentifier():
        raise ValueError("auth_config.session_secret_env must be a valid environment variable name")
    return {
        "required": True,
        "protectedPaths": sorted(set(protected_paths)),
        "publicPaths": ["/api/health", "/api/auth/login", "/api/auth/logout", "/api/auth/signup", "/api/auth/me"],
        "sessionSecretEnv": session_secret_env,
    }


def _protected_paths_from_routes(api_routes: Sequence[Mapping[str, Any]] | None) -> list[str]:
    if not api_routes:
        return ["/api"]

    paths = []
    for route in api_routes:
        if not isinstance(route, Mapping):
            raise ValueError("each api route must be a dictionary")
        path = route.get("path")
        if not isinstance(path, str) or not path.startswith("/api/"):
            raise ValueError("api routes used for auth must have /api/ paths")
        if path in {"/api/health"} or path.startswith("/api/auth"):
            continue
        paths.append(path.split("/:", maxsplit=1)[0])
    return paths or ["/api"]


_SERVER_AUTH_TEMPLATE = r'''
/*
 * Session authentication for the generated Express API.
 *
 * Required packages: npm install bcryptjs express-session
 * Integration in server/index.js, after `pool` and JSON middleware exist and
 * before generated API routes are registered:
 *
 *   import { configureAuth } from "./auth.js";
 *   await configureAuth(app, pool);
 */
import bcrypt from "bcryptjs";
import session from "express-session";
import { Router } from "express";

const authConfig = __AUTH_CONFIG__;

export async function configureAuth(app, pool) {
  const sessionSecret = process.env[authConfig.sessionSecretEnv];
  if (!sessionSecret) {
    throw new Error(`${authConfig.sessionSecretEnv} must be set when authentication is enabled.`);
  }

  await ensureUserTable(pool);
  app.use(session({
    secret: sessionSecret,
    resave: false,
    saveUninitialized: false,
    cookie: { httpOnly: true, sameSite: "lax", secure: process.env.NODE_ENV === "production" },
  }));
  app.use("/api/auth", createAuthRouter(pool));
  const middleware = requireAuth(authConfig.publicPaths);
  for (const path of authConfig.protectedPaths) app.use(path, middleware);
}

export function requireAuth(publicPaths = []) {
  return (req, res, next) => {
    const requestPath = req.originalUrl.split("?", 1)[0];
    if (publicPaths.includes(requestPath)) return next();
    if (!req.session?.userId) return res.status(401).json({ error: "Authentication required" });
    return next();
  };
}

export function createAuthRouter(pool) {
  const router = Router();

  router.post("/signup", async (req, res) => {
    const { email, password } = req.body || {};
    if (!isValidCredentials(email, password)) return res.status(400).json({ error: "Email and an 8-character password are required" });
    try {
      const passwordHash = await bcrypt.hash(password, 12);
      const result = await pool.query(
        "INSERT INTO app_users (email, password_hash) VALUES ($1, $2) RETURNING id, email, created_at",
        [normaliseEmail(email), passwordHash]
      );
      const user = result.rows[0];
      req.session.userId = user.id;
      return res.status(201).json({ user: serialiseUser(user) });
    } catch (error) {
      if (error.code === "23505") return res.status(409).json({ error: "An account with that email already exists" });
      console.error(error);
      return res.status(500).json({ error: "Authentication operation failed" });
    }
  });

  router.post("/login", async (req, res) => {
    const { email, password } = req.body || {};
    if (!isValidCredentials(email, password)) return res.status(400).json({ error: "Email and password are required" });
    try {
      const result = await pool.query("SELECT id, email, password_hash, created_at FROM app_users WHERE email = $1", [normaliseEmail(email)]);
      const user = result.rows[0];
      if (!user || !(await bcrypt.compare(password, user.password_hash))) {
        return res.status(401).json({ error: "Invalid email or password" });
      }
      req.session.userId = user.id;
      return res.json({ user: serialiseUser(user) });
    } catch (error) {
      console.error(error);
      return res.status(500).json({ error: "Authentication operation failed" });
    }
  });

  router.post("/logout", (req, res) => {
    req.session.destroy((error) => {
      if (error) return res.status(500).json({ error: "Could not end session" });
      res.clearCookie("connect.sid");
      return res.status(204).end();
    });
  });

  router.get("/me", async (req, res) => {
    if (!req.session?.userId) return res.status(401).json({ error: "Authentication required" });
    try {
      const result = await pool.query("SELECT id, email, created_at FROM app_users WHERE id = $1", [req.session.userId]);
      if (!result.rowCount) return res.status(401).json({ error: "Authentication required" });
      return res.json({ user: serialiseUser(result.rows[0]) });
    } catch (error) {
      console.error(error);
      return res.status(500).json({ error: "Authentication operation failed" });
    }
  });

  return router;
}

async function ensureUserTable(pool) {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS app_users (
      id BIGSERIAL PRIMARY KEY,
      email TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
  `);
}

function isValidCredentials(email, password) {
  return typeof email === "string" && /^\S+@\S+\.\S+$/.test(email) && typeof password === "string" && password.length >= 8;
}

function normaliseEmail(email) {
  return email.trim().toLowerCase();
}

function serialiseUser(user) {
  return { id: user.id, email: user.email, createdAt: user.created_at };
}
'''


_AUTH_COMPONENT_TEMPLATE = r'''
import { useEffect, useState } from "react";
import { auth } from "./auth.js";
import "./auth.css";

export function AuthPanel({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const result = mode === "login" ? await auth.login({ email, password }) : await auth.signup({ email, password });
      onAuthenticated?.(result.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="auth-panel" aria-labelledby="auth-title">
      <div className="auth-tabs">
        <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Log in</button>
        <button className={mode === "signup" ? "active" : ""} onClick={() => setMode("signup")}>Sign up</button>
      </div>
      <h2 id="auth-title">{mode === "login" ? "Welcome back" : "Create your account"}</h2>
      {error && <div className="alert">{error}</div>}
      <form className="auth-form" onSubmit={submit}>
        <label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required /></label>
        <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} minLength="8" required /></label>
        <button className="primary" type="submit" disabled={submitting}>{submitting ? "Working..." : mode === "login" ? "Log in" : "Sign up"}</button>
      </form>
    </section>
  );
}

export function AuthGate({ children }) {
  const [user, setUser] = useState(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    auth.me().then((result) => setUser(result.user)).catch(() => null).finally(() => setChecked(true));
  }, []);

  if (!checked) return <div className="auth-loading">Loading...</div>;
  if (!user) return <AuthPanel onAuthenticated={setUser} />;
  return children;
}
'''


_AUTH_CLIENT_TEMPLATE = r'''
async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `Request failed: ${response.status}`);
  }
  if (response.status === 204) return null;
  return response.json();
}

export const auth = {
  login: (payload) => request("/api/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  signup: (payload) => request("/api/auth/signup", { method: "POST", body: JSON.stringify(payload) }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  me: () => request("/api/auth/me"),
};
'''


_AUTH_STYLES_TEMPLATE = r'''
.auth-panel { width: min(100% - 28px, 420px); margin: 56px auto; background: white; border: 1px solid #d9dee7; border-radius: 8px; padding: 24px; box-shadow: 0 1px 2px rgba(15, 23, 42, .04); }
.auth-panel h2 { margin: 18px 0; font-size: 24px; }
.auth-tabs { display: flex; gap: 8px; }
.auth-tabs button { flex: 1; }
.auth-form { display: grid; gap: 14px; }
.auth-form label { display: grid; gap: 6px; color: #334155; font-size: 13px; font-weight: 700; }
.auth-form input { min-height: 42px; width: 100%; border: 1px solid #cbd5e1; border-radius: 6px; padding: 10px 12px; background: #fbfdff; }
.auth-panel .primary { width: 100%; background: #2563eb; color: white; }
.auth-panel .alert { margin: 12px 0; border: 1px solid #fecaca; background: #fff1f2; color: #9f1239; border-radius: 8px; padding: 12px 14px; }
.auth-loading { max-width: 420px; margin: 56px auto; color: #64748b; text-align: center; }
'''


if __name__ == "__main__":
    no_auth = scaffold_auth(False)
    auth_required = scaffold_auth(
        {"required": True, "protected_paths": ["/api/items"]},
        [{"method": "GET", "path": "/api/items"}],
    )
    print(f"No-auth files: {sorted(no_auth)}")
    print(f"Auth files: {sorted(auth_required)}")
