# ReferME — Product Requirements

## App Concept
A three-sided marketplace mobile app (Expo React Native) connecting **Students**, **Professionals**, and **Employers**, with credits, leaderboards, and INR payouts.

## Roles
- **Student** — buys credits, books mock interviews with professionals, applies for referrals.
- **Professional** — conducts interviews (+25 credits), refers candidates (+500 credits if hired), redeems credits as INR.
- **Employer** — posts jobs (individual / bulk), views candidates, marks hires.
- **Admin** — manages users, approves payouts, resolves disputes.

## Core Modules Implemented
1. **Auth** — JWT signup + email OTP, login, forgot/reset password, Emergent Google login endpoint.
2. **Profile setup** — 3 role variants with completion flag.
3. **Dashboards** — role-specific tabs (home, sub-screens).
4. **Wallet & Credits** — balance, transactions, deposit (Razorpay mock), 1 free referral + 1 free interview.
5. **Subscription** — first deposit ₹199 → 398 credits, thereafter 1₹ = 1 credit; each action costs 49.
6. **Mock interviews** — pro creates slot, student books (cost 49), pro marks complete (+25).
7. **Referrals & Jobs** — student applies (cost 49), professional refers, employer hires → +500 to referrer.
8. **Leaderboards** — students (interviews + resume score), professionals (interviews + referrals).
9. **Payouts** — min 500 credits, admin approve/reject, credits held on request, refunded on reject.
10. **Admin** — stats dashboard, users list, payouts queue, disputes resolution.

## Mocks Active
- **MOCK_OTP_MODE** — signup/forgot returns OTP in response (no SendGrid key set).
- **MOCK_PAYMENTS_MODE** — Razorpay signature check skipped; instant credit on confirm.

## Tech Stack
- **Frontend**: Expo Router, React Native, expo-linear-gradient, @expo/vector-icons (Ionicons), react-native-safe-area-context.
- **Backend**: FastAPI + Motor (MongoDB), JWT (PyJWT), bcrypt password hashing, httpx for Emergent Google session exchange.

## Endpoints (`/api/*`)
- Auth: `/auth/signup`, `/auth/verify-otp`, `/auth/login`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/google`, `/auth/me`
- Profile: `PUT /profile`
- Wallet: `/wallet`, `/wallet/deposit/create-order`, `/wallet/deposit/confirm`, `/subscription/plans`
- Interviews: `/professionals`, `/interviews/slots`, `/interviews/book`, `/interviews/{id}/complete`
- Jobs/Referrals/Apps: `/jobs`, `/jobs/apply`, `/referrals`, `/applications`, `/applications/hire`
- Leaderboards: `/leaderboard/students`, `/leaderboard/professionals`
- Payouts: `/payouts/request`, `/payouts`, `/admin/payouts/action`
- Admin: `/admin/users`, `/admin/stats`
- Disputes: `/disputes`, `/admin/disputes/{id}/resolve`
- Notifications: `/notifications`, `/notifications/read-all`

## Seed Data
- Admin: `admin@referme.app` / `Admin@12345`
- Demo employer with 3 sample jobs auto-seeded on startup.
