-- 1. Enable UUID extension if not enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. Create Custom Enum for User Roles
DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('candidate', 'recruiter');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 3. Create public.users Table (Syncs with auth.users)
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

-- 4. Create public.candidate_profiles Table
CREATE TABLE IF NOT EXISTS public.candidate_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    full_name TEXT,
    resume_url TEXT,
    experience_years INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 5. Create public.recruiter_profiles Table
CREATE TABLE IF NOT EXISTS public.recruiter_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    company_name TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 6. Trigger Function to auto-populate public.users and Profiles upon Signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
    user_role_val user_role;
    user_first_name TEXT;
    user_last_name TEXT;
    user_full_name TEXT;
BEGIN
    user_role_val := COALESCE((new.raw_user_meta_data->>'role')::user_role, 'candidate'::user_role);
    user_first_name := COALESCE(new.raw_user_meta_data->>'first_name', '');
    user_last_name := COALESCE(new.raw_user_meta_data->>'last_name', '');
    user_full_name := COALESCE(new.raw_user_meta_data->>'full_name', TRIM(CONCAT(user_first_name, ' ', user_last_name)));

    -- Insert into public.users
    INSERT INTO public.users (id, email, first_name, last_name, full_name, role)
    VALUES (new.id, new.email, user_first_name, user_last_name, user_full_name, user_role_val)
    ON CONFLICT (id) DO UPDATE 
    SET email = EXCLUDED.email,
        full_name = EXCLUDED.full_name,
        updated_at = timezone('utc'::text, now());

    -- Insert into role-specific profile
    IF user_role_val = 'recruiter' THEN
        INSERT INTO public.recruiter_profiles (user_id, company_name)
        VALUES (new.id, COALESCE(new.raw_user_meta_data->>'company_name', ''))
        ON CONFLICT DO NOTHING;
    ELSE
        INSERT INTO public.candidate_profiles (user_id, email, full_name)
        VALUES (new.id, new.email, user_full_name)
        ON CONFLICT DO NOTHING;
    END IF;

    RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 7. Attach Trigger to auth.users table
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 8. Enable Row Level Security (RLS)
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.candidate_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recruiter_profiles ENABLE ROW LEVEL SECURITY;

-- 9. Row Level Security Policies
CREATE POLICY "Users can view own record" ON public.users FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own record" ON public.users FOR UPDATE USING (auth.uid() = id);

CREATE POLICY "Candidates can view own profile" ON public.candidate_profiles FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Candidates can update own profile" ON public.candidate_profiles FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Recruiters can view own profile" ON public.recruiter_profiles FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Recruiters can update own profile" ON public.recruiter_profiles FOR UPDATE USING (auth.uid() = user_id);
