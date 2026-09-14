-- ================================================================
-- Migration 005: Fix Auth Signup Trigger & User Profiles Sync
-- Vetra AI Technical Interviewer
-- Execute this script in your Supabase SQL Editor to resolve:
-- "Database error saving new user" (HTTP 400 on /auth/signup)
-- ================================================================

-- 1. Ensure user_role enum exists with correct values
DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('candidate', 'recruiter');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 2. Ensure public.users table structure
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    first_name TEXT,
    last_name TEXT,
    full_name TEXT,
    role user_role NOT NULL DEFAULT 'candidate',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 3. Ensure candidate_profiles and recruiter_profiles tables exist with unique user_id
CREATE TABLE IF NOT EXISTS public.candidate_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    full_name TEXT,
    resume_url TEXT,
    experience_years INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.recruiter_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    company_name TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Ensure user_id unique indexes for ON CONFLICT support
CREATE UNIQUE INDEX IF NOT EXISTS idx_candidate_profiles_user_id ON public.candidate_profiles(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_recruiter_profiles_user_id ON public.recruiter_profiles(user_id);

-- 4. Robust Trigger Function for auto-syncing auth.users -> public.users & profiles
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER 
LANGUAGE plpgsql 
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    user_role_val user_role;
    user_first_name TEXT;
    user_last_name TEXT;
    user_full_name TEXT;
    raw_role TEXT;
BEGIN
    -- Safely parse role
    raw_role := LOWER(COALESCE(new.raw_user_meta_data->>'role', 'candidate'));
    IF raw_role = 'recruiter' THEN
        user_role_val := 'recruiter'::user_role;
    ELSE
        user_role_val := 'candidate'::user_role;
    END IF;

    -- Safely parse names
    user_first_name := COALESCE(new.raw_user_meta_data->>'first_name', '');
    user_last_name := COALESCE(new.raw_user_meta_data->>'last_name', '');
    user_full_name := COALESCE(
        new.raw_user_meta_data->>'full_name',
        NULLIF(TRIM(CONCAT(user_first_name, ' ', user_last_name)), '')
    );
    IF user_full_name IS NULL OR user_full_name = '' THEN
        user_full_name := split_part(COALESCE(new.email, 'User'), '@', 1);
    END IF;

    -- Insert or update public.users
    INSERT INTO public.users (id, email, first_name, last_name, full_name, role)
    VALUES (new.id, COALESCE(new.email, ''), user_first_name, user_last_name, user_full_name, user_role_val)
    ON CONFLICT (id) DO UPDATE 
    SET email = EXCLUDED.email,
        first_name = EXCLUDED.first_name,
        last_name = EXCLUDED.last_name,
        full_name = EXCLUDED.full_name,
        role = EXCLUDED.role,
        updated_at = timezone('utc'::text, now());

    -- Insert into role-specific profile
    IF user_role_val = 'recruiter' THEN
        INSERT INTO public.recruiter_profiles (user_id, company_name)
        VALUES (new.id, COALESCE(new.raw_user_meta_data->>'company_name', ''))
        ON CONFLICT (user_id) DO NOTHING;
    ELSE
        INSERT INTO public.candidate_profiles (user_id, email, full_name)
        VALUES (new.id, COALESCE(new.email, ''), user_full_name)
        ON CONFLICT (user_id) DO NOTHING;
    END IF;

    RETURN new;
EXCEPTION
    WHEN OTHERS THEN
        -- Prevent registration transaction from failing if a non-critical error occurs
        RAISE WARNING 'handle_new_user trigger error: %', SQLERRM;
        RETURN new;
END;
$$;

-- 5. Re-attach Trigger to auth.users
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 6. Grant necessary table permissions
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA public TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated;
