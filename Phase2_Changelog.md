# Phase 2: User Authentication & Data Persistence - Technical Changelog

## Table of Contents
1. [Overview](#overview)
2. [Stage 1: Infrastructure + Core Auth](#stage-1-infrastructure--core-auth)
3. [Stage 2: Storage + Job Persistence](#stage-2-storage--job-persistence)
4. [Stage 3: Frontend Auth](#stage-3-frontend-auth)
5. [Stage 4: Dashboard + History UI](#stage-4-dashboard--history-ui)
6. [API Reference](#api-reference)
7. [Database Schema](#database-schema)
8. [Technology Deep Dive](#technology-deep-dive)
9. [AWS Deployment Guide](#aws-deployment-guide)

---

## Overview

**Goal**: Transform the application from a stateless document processor into a multi-user platform with persistent storage, authentication, and user dashboards.

**Why Phase 2 Was Needed**:
- **Problem**: Previously, processing results were lost after each session. No user accounts meant no data ownership or history tracking.
- **Solution**: Implement authentication, persistent storage, and user-specific dashboards to enable production use.

---

## Stage 1: Infrastructure + Core Auth

### Goal
Establish database and authentication foundation to support multi-user functionality.

### What Was Implemented

#### 1. Docker Infrastructure Updates
**File**: `docker-compose.yml`

**Changes**:
```yaml
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: metadata_tagger
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-BASH", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_data:/data
```

**Why**:
- **PostgreSQL**: Chosen for ACID compliance, complex queries (joins, aggregations), and JSONB support for flexible metadata storage
- **MinIO**: S3-compatible object storage for PDF files, avoiding filesystem complexity and enabling cloud migration
- **Health Checks**: Ensure database is ready before backend starts, preventing connection errors

#### 2. Database Schema
**File**: `backend/app/database/schema.sql`

**Tables Created**:

```sql
-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Refresh tokens for JWT rotation
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(512) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Processing jobs
CREATE TABLE processing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    total_documents INTEGER DEFAULT 0,
    processed_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    config JSONB,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Individual documents
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES processing_jobs(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    title VARCHAR(500) NOT NULL,
    file_path TEXT NOT NULL,
    file_source_type VARCHAR(50) NOT NULL,
    file_size BIGINT,
    mime_type VARCHAR(100),
    status VARCHAR(50) DEFAULT 'pending',
    tags JSONB DEFAULT '[]',
    extracted_text TEXT,
    processing_metadata JSONB,
    error_message TEXT,
    processed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_expires_at ON refresh_tokens(expires_at);
CREATE INDEX idx_jobs_user_id ON processing_jobs(user_id);
CREATE INDEX idx_jobs_status ON processing_jobs(status);
CREATE INDEX idx_documents_job_id ON documents(job_id);
CREATE INDEX idx_documents_user_id ON documents(user_id);
CREATE INDEX idx_documents_status ON documents(status);
```

**Schema Design Decisions**:
- **UUID Primary Keys**: Distributed system friendly, no collision risk, harder to enumerate
- **JSONB for tags/metadata**: Flexible schema for varying tag structures across languages
- **Cascading Deletes**: Job deletion removes all documents; user deletion nullifies references
- **Timestamps**: Track creation/update for auditing and debugging
- **Indexes**: Optimize common queries (user jobs, document searches, token lookups)

#### 3. Database Connection Manager
**File**: `backend/app/database/connection.py`

```python
class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            host=settings.DATABASE_HOST,
            port=settings.DATABASE_PORT,
            user=settings.DATABASE_USER,
            password=settings.DATABASE_PASSWORD,
            database=settings.DATABASE_NAME,
            min_size=5,
            max_size=20
        )
```

**Why Async Connection Pooling**:
- **Performance**: Reuses connections instead of creating new ones per request
- **Concurrency**: Async allows handling multiple requests without blocking
- **Resource Management**: Pool limits prevent database overload

#### 4. Authentication Service
**File**: `backend/app/services/auth_service.py`

**Key Components**:

```python
class AuthService:
    # Password hashing with bcrypt
    def hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    # JWT token generation
    def create_access_token(self, data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire, "type": "access"})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    def create_refresh_token(self, data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
```

**Technology Choices**:
- **Bcrypt**: Adaptive hashing with salt, resistant to rainbow tables and GPU attacks
- **JWT**: Stateless authentication, no server-side session storage needed
- **Refresh Tokens**: Long-lived tokens stored in DB for rotation, short-lived access tokens for security

#### 5. User Repository
**File**: `backend/app/repositories/user_repository.py`

Repository pattern separates data access logic from business logic:

```python
class UserRepository:
    async def create_user(self, email: str, password_hash: str, full_name: str = None):
        query = """
            INSERT INTO users (email, password_hash, full_name)
            VALUES ($1, $2, $3)
            RETURNING id, email, full_name, is_active, created_at
        """
        return await self.db.fetchrow(query, email, password_hash, full_name)

    async def get_user_by_email(self, email: str):
        query = "SELECT * FROM users WHERE email = $1"
        return await self.db.fetchrow(query, email)
```

**Why Repository Pattern**:
- **Separation of Concerns**: Business logic doesn't need SQL knowledge
- **Testability**: Easy to mock for unit tests
- **Maintainability**: Database changes isolated to repository layer

#### 6. Authentication Endpoints
**File**: `backend/app/routers/auth.py`

**Endpoints Created**:

```python
@router.post("/register")
async def register(user: UserRegister):
    # Hash password, create user, return tokens

@router.post("/login")
async def login(credentials: UserLogin):
    # Verify password, create tokens, return user data

@router.post("/refresh")
async def refresh_token(refresh: RefreshTokenRequest):
    # Validate refresh token, issue new access token

@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_active_user)):
    # Invalidate refresh token

@router.get("/me")
async def get_current_user(current_user: dict = Depends(get_current_active_user)):
    # Return current user profile
```

#### 7. Configuration Updates
**File**: `backend/app/config.py`

```python
class Settings(BaseSettings):
    # Database
    DATABASE_HOST: str = "postgres"
    DATABASE_PORT: int = 5432
    DATABASE_USER: str = "postgres"
    DATABASE_PASSWORD: str = "postgres"
    DATABASE_NAME: str = "metadata_tagger"

    # MinIO
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "documents"

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
```

#### 8. Dependencies
**File**: `backend/requirements.txt`

Added:
```
asyncpg==0.29.0          # PostgreSQL async driver
python-jose[cryptography]==3.3.0  # JWT encoding/decoding
bcrypt==4.0.1            # Password hashing
passlib==1.7.4           # Password context management
email-validator==2.1.0   # Email validation
minio==7.2.0             # Object storage client
```

### How It Works

1. **Registration Flow**:
   - User submits email/password
   - Password hashed with bcrypt (10 rounds)
   - User record created in database
   - Access + refresh tokens generated
   - Tokens returned to client

2. **Login Flow**:
   - User submits credentials
   - Email lookup in database
   - Password verification with bcrypt
   - New tokens generated
   - Old refresh tokens invalidated

3. **Token Refresh Flow**:
   - Client sends refresh token
   - Token validated (signature, expiration, database presence)
   - New access token issued
   - Refresh token optionally rotated

4. **Protected Routes**:
   - Client sends access token in Authorization header
   - FastAPI dependency extracts and validates token
   - User ID embedded in token used for queries

### Deliverable
✅ Users can register and login via API with secure JWT authentication

---

## Stage 2: Storage + Job Persistence

### Goal
Make processing results permanent by integrating object storage and database persistence.

### What Was Implemented

#### 1. MinIO Storage Service
**File**: `backend/app/services/storage_service.py`

```python
class StorageService:
    def __init__(self):
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=False
        )
        self._ensure_bucket()

    async def upload_file(self, file_data: bytes, object_name: str, content_type: str = "application/pdf"):
        """Upload file to MinIO"""

    async def download_file(self, object_name: str) -> bytes:
        """Download file from MinIO"""

    async def get_presigned_url(self, object_name: str, expires: int = 3600) -> str:
        """Generate temporary download URL"""

    async def delete_file(self, object_name: str):
        """Delete file from storage"""
```

**Why MinIO**:
- **S3 Compatible**: Easy migration to AWS S3 later
- **Self-Hosted**: No external dependencies or costs
- **Scalable**: Handles large files better than filesystem
- **URL Generation**: Temporary signed URLs for secure downloads

#### 2. Job Repository
**File**: `backend/app/repositories/job_repository.py`

```python
class JobRepository:
    async def create_job(self, user_id: UUID, job_type: str, config: dict):
        """Create new processing job"""

    async def update_job_status(self, job_id: UUID, status: str,
                                processed_count: int, failed_count: int):
        """Update job progress"""

    async def get_jobs_by_user(self, user_id: UUID, limit: int, offset: int):
        """Retrieve user's job history with pagination"""

    async def delete_job(self, job_id: UUID):
        """Delete job and cascade to documents"""
```

**Why Separate Repository**:
- **Reusability**: Multiple services can use job operations
- **Transaction Management**: Atomic operations for job updates
- **Query Optimization**: Centralized query tuning

#### 3. Document Repository
**File**: `backend/app/repositories/document_repository.py`

```python
class DocumentRepository:
    async def create_document(self, job_id: UUID, user_id: UUID,
                              title: str, file_path: str, file_source_type: str):
        """Create document record"""

    async def update_document_result(self, doc_id: UUID, status: str,
                                     tags: List[str], extracted_text: str,
                                     processing_metadata: dict):
        """Store processing results"""

    async def get_documents_by_job(self, job_id: UUID):
        """Get all documents for a job"""

    async def search_documents(self, user_id: UUID, query_text: str, limit: int):
        """Search documents by title or tags"""
```

**Search Implementation**:
```sql
SELECT * FROM documents
WHERE user_id = $1
  AND (
      title ILIKE $2       -- Case-insensitive title search
      OR tags::text ILIKE $2  -- Search within JSONB tags
  )
ORDER BY processed_at DESC NULLS LAST
LIMIT $3
```

**Why JSONB for Tags**:
- **Flexibility**: Different languages have different tag structures
- **Queryability**: PostgreSQL can index and search JSONB efficiently
- **No Schema Changes**: Add new tag types without migrations

#### 4. Batch Processor Integration
**File**: `backend/app/services/async_batch_processor.py`

**Changes**:

```python
@dataclass
class BatchJob:
    job_id: str
    # Added for persistence:
    db_job_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    document_ids: List[UUID] = field(default_factory=list)

async def _update_job_status_db(self, job: BatchJob, status: str, error: Optional[str] = None):
    """Update job status in database"""
    if not job.db_job_id:
        return

    await self.job_repo.update_job_status(
        job_id=job.db_job_id,
        status=status,
        processed_count=job.completed,
        failed_count=job.failed,
        error_message=error
    )

async def _update_document_result_db(self, job: BatchJob, doc_idx: int,
                                     status: str, tags: List[str], ...):
    """Store document processing result"""
    if doc_idx >= len(job.document_ids):
        return

    doc_id = job.document_ids[doc_idx]
    await self.doc_repo.update_document_result(
        doc_id=doc_id,
        status=status,
        tags=tags,
        extracted_text=extracted_text,
        processing_metadata=metadata
    )
```

**Integration Points**:
- Job created in DB before processing starts
- Documents created with "pending" status
- Progress updates after each document
- Final status update on completion/failure

#### 5. Single Processing Updates
**File**: `backend/app/routers/single.py`

```python
@router.post("/process-single")
async def process_single(
    request: ProcessRequest,
    current_user: Optional[dict] = Depends(get_optional_user)  # Optional auth
):
    # ... existing processing ...

    # NEW: Persist to database if user is authenticated
    if current_user:
        job = await job_repo.create_job(
            user_id=current_user["id"],
            job_type="single",
            config={"url": request.url, ...}
        )

        doc = await doc_repo.create_document(
            job_id=job["id"],
            user_id=current_user["id"],
            title=request.url.split("/")[-1],
            file_path=request.url,
            file_source_type="url"
        )

        await doc_repo.update_document_result(
            doc_id=doc["id"],
            status="success",
            tags=result.tags,
            extracted_text=result.extracted_text
        )
```

**Why Optional Auth**:
- **Backward Compatibility**: Anonymous users can still process
- **Progressive Enhancement**: Logged-in users get history
- **Conversion Funnel**: Anonymous users see value before registering

#### 6. History Endpoints
**File**: `backend/app/routers/history.py`

```python
@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
    current_user: Optional[dict] = Depends(get_optional_user)
):
    """List jobs (user-specific if authenticated)"""

@router.get("/jobs/{job_id}", response_model=JobDetail)
async def get_job_detail(job_id: UUID, current_user: Optional[dict] = ...):
    """Get job with all documents"""

@router.delete("/jobs/{job_id}")
async def delete_job(job_id: UUID, current_user: dict = Depends(get_current_active_user)):
    """Delete job (auth required)"""

@router.get("/documents", response_model=DocumentListResponse)
async def list_recent_documents(limit: int = 50, current_user: Optional[dict] = ...):
    """List recent documents"""
```

**Authorization Logic**:
```python
# Check ownership before allowing access
if current_user and job["user_id"] and job["user_id"] != current_user["id"]:
    raise HTTPException(status_code=403, detail="Not authorized")
```

### How It Works

1. **Processing with Persistence**:
   - User starts processing job
   - Job record created in `processing_jobs` table
   - Document records created in `documents` table with "pending" status
   - Files uploaded to MinIO with UUID-based paths
   - Processing results update document records
   - Job status updated on completion

2. **Storage Architecture**:
   ```
   MinIO Bucket Structure:
   documents/
     ├── <user_id>/
     │   ├── <job_id>/
     │   │   ├── <doc_id>.pdf
   ```

3. **Query Optimization**:
   - Indexes on `user_id`, `job_id`, `status` for fast lookups
   - Pagination prevents large result sets
   - JSONB indexes for tag searches

### Deliverable
✅ Processing jobs and results saved to database with file storage in MinIO

---

## Stage 3: Frontend Auth

### Goal
Enable users to login from the UI and access protected features.

### What Was Implemented

#### 1. Auth State Management
**File**: `frontend/lib/authStore.ts`

```typescript
interface AuthState {
  user: User | null;
  tokens: AuthTokens | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshTokens: () => Promise<void>;
  getAccessToken: () => string | null;
  isTokenExpired: () => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      tokens: null,
      isAuthenticated: false,
      // ... implementation
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        tokens: state.tokens,
        isAuthenticated: state.isAuthenticated
      })
    }
  )
)
```

**Why Zustand**:
- **Simplicity**: Less boilerplate than Redux
- **Performance**: Only re-renders subscribed components
- **Persistence**: Built-in localStorage sync
- **TypeScript**: First-class TypeScript support

**Persistence Strategy**:
- Tokens stored in localStorage
- Automatically rehydrated on page load
- Cleared on logout

#### 2. Login Page
**File**: `frontend/app/login/page.tsx`

```typescript
export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const { login, isLoading, error } = useAuthStore()
  const router = useRouter()

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    try {
      await login(email, password)
      router.push('/dashboard')
    } catch (err) {
      // Error shown via auth store
    }
  }

  // Form UI with email/password inputs
}
```

**UX Features**:
- Loading state during authentication
- Error messages displayed inline
- Link to registration page
- Email validation

#### 3. Registration Page
**File**: `frontend/app/register/page.tsx`

```typescript
export default function RegisterPage() {
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    confirmPassword: '',
    fullName: ''
  })

  async function handleSubmit(e: FormEvent) {
    if (formData.password !== formData.confirmPassword) {
      setError('Passwords do not match')
      return
    }

    await register(formData.email, formData.password, formData.fullName)
    router.push('/dashboard')
  }
}
```

**Validation**:
- Email format validation
- Password confirmation match
- Minimum password length (handled by backend)

#### 4. API Client with Auth Interceptor
**File**: `frontend/lib/api.ts`

```typescript
function getAuthHeaders(): HeadersInit {
  const token = useAuthStore.getState().getAccessToken()
  return token ? { 'Authorization': `Bearer ${token}` } : {}
}

async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const authHeaders = getAuthHeaders()
  const response = await fetch(url, {
    ...options,
    headers: { ...authHeaders, ...options.headers }
  })

  // Token refresh on 401
  if (response.status === 401) {
    const refreshed = await useAuthStore.getState().refreshTokens()
    if (refreshed) {
      // Retry with new token
      const retryHeaders = getAuthHeaders()
      return fetch(url, {
        ...options,
        headers: { ...retryHeaders, ...options.headers }
      })
    }
  }

  return response
}
```

**Why Interceptor Pattern**:
- **Automatic Token Attachment**: All API calls include auth header
- **Token Refresh**: Transparently renews expired tokens
- **Error Handling**: Centralized 401 handling
- **DRY**: No need to manually add headers per request

#### 5. Protected Route Component
**File**: `frontend/components/ProtectedRoute.tsx`

```typescript
export default function ProtectedRoute({ children, fallback }: ProtectedRouteProps) {
  const router = useRouter()
  const { isAuthenticated, isLoading } = useAuthStore()
  const [isHydrated, setIsHydrated] = useState(false)

  // Wait for hydration to avoid flash
  useEffect(() => {
    setIsHydrated(true)
  }, [])

  useEffect(() => {
    if (isHydrated && !isLoading && !isAuthenticated) {
      router.push('/login')
    }
  }, [isHydrated, isAuthenticated, isLoading, router])

  if (!isHydrated || isLoading) {
    return fallback || <LoadingSpinner />
  }

  if (!isAuthenticated) {
    return fallback || <LoadingSpinner />
  }

  return <>{children}</>
}
```

**Hydration Handling**:
- **Problem**: localStorage is only available client-side
- **Solution**: Wait for hydration before checking auth state
- **UX**: Show loading spinner instead of flash of wrong content

#### 6. Header with User Menu
**File**: `frontend/components/Header.tsx`

```typescript
export default function Header() {
  const { user, isAuthenticated, logout } = useAuthStore()
  const [dropdownOpen, setDropdownOpen] = useState(false)

  return (
    <header>
      {isAuthenticated ? (
        <div className="user-menu">
          <button onClick={() => setDropdownOpen(!dropdownOpen)}>
            <Avatar>{user?.full_name?.[0] || user?.email?.[0]}</Avatar>
            {user?.full_name || user?.email?.split('@')[0]}
          </button>

          {dropdownOpen && (
            <Dropdown>
              <Link href="/dashboard">Dashboard</Link>
              <Link href="/history">History</Link>
              <Link href="/documents">Search Documents</Link>
              <button onClick={logout}>Sign Out</button>
            </Dropdown>
          )}
        </div>
      ) : (
        <>
          <Link href="/login">Sign In</Link>
          <Link href="/register">Get Started</Link>
        </>
      )}
    </header>
  )
}
```

**Navigation Links**:
- Desktop: Shown in header nav bar
- Mobile: Available in dropdown menu
- Conditional rendering based on auth state

#### 7. Layout Integration
**File**: `frontend/app/layout.tsx`

```typescript
import Header from '@/components/Header'

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <Header />
        <main>{children}</main>
        <footer>...</footer>
      </body>
    </html>
  )
}
```

### How It Works

1. **Login Flow**:
   - User enters credentials → form submission
   - `authStore.login()` calls `/api/auth/login`
   - Backend validates, returns tokens + user data
   - Store updates state, persists to localStorage
   - Router redirects to dashboard
   - Subsequent requests include Bearer token

2. **Token Lifecycle**:
   ```
   Access Token (30 min) ──┐
                          ├─→ Used for API requests
   Refresh Token (7 days)─┘    Renewed when access expires
   ```

3. **Protected Route Flow**:
   ```
   User navigates to /dashboard
   → ProtectedRoute wrapper checks auth
   → If not authenticated → redirect to /login
   → If authenticated → render dashboard
   ```

4. **Auto-Refresh**:
   - Access token expires after 30 minutes
   - API request returns 401
   - Interceptor calls refresh endpoint with refresh token
   - New access token obtained
   - Original request retried

### Deliverable
✅ Full login/logout flow in the UI with protected routes and automatic token refresh

---

## Stage 4: Dashboard + History UI

### Goal
Provide users visibility into their processing history and statistics.

### What Was Implemented

#### 1. Dashboard Statistics Endpoint
**File**: `backend/app/routers/history.py`

```python
@router.get("/stats", response_model=UserStats)
async def get_user_stats(current_user: dict = Depends(get_current_active_user)):
    """Calculate user statistics"""
    jobs = await job_repo.get_jobs_by_user(user_id, limit=1000, offset=0)

    return UserStats(
        total_jobs=len(jobs),
        total_documents=sum(j["total_documents"] for j in jobs),
        documents_processed=sum(j["processed_count"] for j in jobs),
        documents_failed=sum(j["failed_count"] for j in jobs),
        jobs_by_status={
            status: count for status, count in
            Counter(j["status"] for j in jobs).items()
        },
        recent_activity=jobs[:5]
    )
```

**Why Compute Stats on Request**:
- **Real-time**: Always shows current data
- **Simple**: No separate aggregation tables to maintain
- **Scalable**: Pagination limits query size

#### 2. Document Search Endpoint
**File**: `backend/app/routers/history.py`

```python
@router.get("/documents/search")
async def search_documents(
    query: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict = Depends(get_current_active_user)
):
    """Search user's documents by title or tags"""
    documents = await doc_repo.search_documents(user_id, query, limit)
    return DocumentListResponse(documents=doc_summaries, total=len(doc_summaries))
```

**Repository Implementation**:
```python
async def search_documents(self, user_id: UUID, query_text: str, limit: int):
    search_pattern = f"%{query_text}%"
    query = """
        SELECT * FROM documents
        WHERE user_id = $1
          AND (title ILIKE $2 OR tags::text ILIKE $2)
        ORDER BY processed_at DESC NULLS LAST
        LIMIT $3
    """
    return await self.db.fetch(query, user_id, search_pattern, limit)
```

**ILIKE for Search**:
- Case-insensitive matching
- `%` wildcards for partial matches
- JSONB cast to text for tag searching

#### 3. Dashboard Page
**File**: `frontend/app/dashboard/page.tsx`

**Components**:
```typescript
function DashboardContent() {
  const [stats, setStats] = useState<UserStats | null>(null)

  useEffect(() => {
    getUserStats().then(setStats)
  }, [])

  return (
    <>
      {/* Welcome Banner */}
      <WelcomeBanner user={user} />

      {/* Stats Grid */}
      <StatsGrid>
        <StatCard title="Total Jobs" value={stats.total_jobs} />
        <StatCard title="Processed" value={stats.documents_processed} />
        <StatCard title="Failed" value={stats.documents_failed} />
        <StatCard title="Success Rate" value={`${successRate}%`} />
      </StatsGrid>

      {/* Quick Actions */}
      <QuickActions>
        <ActionCard href="/" title="New Processing Job" />
        <ActionCard href="/history" title="View History" />
        <ActionCard href="/documents" title="Search Documents" />
      </QuickActions>

      {/* Recent Activity */}
      <RecentJobsTable jobs={stats.recent_activity} />
    </>
  )
}
```

**Stat Cards**:
- Total jobs processed
- Documents processed (success count)
- Documents failed
- Success rate (calculated: processed/total * 100)

**Quick Actions**:
- Links to common tasks
- Icons for visual clarity
- Hover states for interactivity

#### 4. Enhanced History Page
**File**: `frontend/app/history/page.tsx`

**Filters**:
```typescript
function HistoryContent() {
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [filteredJobs, setFilteredJobs] = useState<JobSummary[]>([])

  // Filter states
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [sortOrder, setSortOrder] = useState<'newest' | 'oldest'>('newest')

  useEffect(() => {
    let result = [...jobs]

    if (statusFilter !== 'all') {
      result = result.filter(j => j.status === statusFilter)
    }

    if (typeFilter !== 'all') {
      result = result.filter(j => j.job_type === typeFilter)
    }

    result.sort((a, b) => {
      const dateA = new Date(a.created_at).getTime()
      const dateB = new Date(b.created_at).getTime()
      return sortOrder === 'newest' ? dateB - dateA : dateA - dateB
    })

    setFilteredJobs(result)
  }, [jobs, statusFilter, typeFilter, sortOrder])
}
```

**Job Detail Modal**:
```typescript
function JobDetailModal({ jobId, onClose }) {
  const [job, setJob] = useState(null)

  useEffect(() => {
    if (jobId) {
      getJobDetail(jobId).then(setJob)
    }
  }, [jobId])

  return (
    <Modal onClose={onClose}>
      <JobInfo job={job} />
      <DocumentList documents={job.documents} />
    </Modal>
  )
}
```

**Features**:
- Filter by status (pending, processing, completed, failed)
- Filter by job type (single, batch)
- Sort by date (newest/oldest first)
- View button opens modal with full job details
- Delete button removes job and documents
- Document cards show tags and status

#### 5. Document Search Page
**File**: `frontend/app/documents/page.tsx`

```typescript
function DocumentsContent() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([])
  const [searchQuery, setSearchQuery] = useState('')

  async function handleSearch() {
    if (!searchQuery.trim()) {
      const response = await getDocuments(50)
      setDocuments(response.documents)
    } else {
      const response = await searchDocuments(searchQuery.trim(), 50)
      setDocuments(response.documents)
    }
  }

  return (
    <>
      <SearchBar
        value={searchQuery}
        onChange={setSearchQuery}
        onSearch={handleSearch}
      />

      <DocumentGrid>
        {documents.map(doc => (
          <DocumentCard
            key={doc.id}
            document={doc}
            onClick={() => setSelectedDocId(doc.id)}
          />
        ))}
      </DocumentGrid>

      <DocumentDetailModal
        docId={selectedDocId}
        onClose={() => setSelectedDocId(null)}
      />
    </>
  )
}
```

**Document Card**:
- Title and file path
- Status badge (success/failed/pending)
- First 6 tags with "+N more" indicator
- Source type and processed date
- Click to view full details

**Document Detail Modal**:
- Full document information
- All tags displayed
- Extracted text preview (first 1000 chars)
- Error message if processing failed
- Processing metadata

#### 6. API Client Extensions
**File**: `frontend/lib/api.ts`

```typescript
export async function getUserStats(): Promise<UserStats> {
  const response = await authFetch(`${API_BASE}/api/history/stats`)
  return handleResponse<UserStats>(response)
}

export async function getDocuments(limit = 50): Promise<DocumentListResponse> {
  const response = await authFetch(
    `${API_BASE}/api/history/documents?limit=${limit}`
  )
  return handleResponse<DocumentListResponse>(response)
}

export async function searchDocuments(
  query: string,
  limit = 50
): Promise<DocumentListResponse> {
  const response = await authFetch(
    `${API_BASE}/api/history/documents/search?query=${encodeURIComponent(query)}&limit=${limit}`
  )
  return handleResponse<DocumentListResponse>(response)
}

export async function getDocumentDetail(docId: string): Promise<any> {
  const response = await authFetch(`${API_BASE}/api/history/documents/${docId}`)
  return handleResponse(response)
}
```

**Type Safety**:
- TypeScript interfaces for all API responses
- Generic `handleResponse<T>` for type checking
- URL encoding for search queries

### How It Works

1. **Dashboard Loading**:
   - User navigates to `/dashboard`
   - `ProtectedRoute` verifies authentication
   - `getUserStats()` fetches statistics
   - React state updated, components re-render
   - Stats cards animate in with values

2. **History Filtering**:
   - All jobs fetched on page load
   - Client-side filtering for instant response
   - Filters update `filteredJobs` state
   - Table re-renders with filtered results

3. **Document Search**:
   - User types query and clicks search
   - Backend performs ILIKE query on title and tags
   - Results filtered by user_id (security)
   - Document cards rendered with tag previews

4. **Modal Navigation**:
   - User clicks "View" on job/document
   - State updated with selected ID
   - Modal fetches detailed data
   - Close button clears selected ID

### Deliverable
✅ Complete user dashboard experience with stats, filterable history, and document search

---

## API Reference

### Authentication Endpoints

#### POST `/api/auth/register`
**Purpose**: Create new user account
**Auth**: None
**Request Body**:
```json
{
  "email": "user@example.com",
  "password": "securepass123",
  "full_name": "John Doe"
}
```
**Response**:
```json
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "full_name": "John Doe",
    "is_active": true
  },
  "access_token": "jwt-token",
  "refresh_token": "jwt-refresh-token"
}
```
**How It Works**: Password hashed with bcrypt, user created in DB, JWT tokens generated

---

#### POST `/api/auth/login`
**Purpose**: Authenticate existing user
**Auth**: None
**Request Body**:
```json
{
  "email": "user@example.com",
  "password": "securepass123"
}
```
**Response**: Same as register
**How It Works**: Email lookup, password verification with bcrypt, tokens generated

---

#### POST `/api/auth/refresh`
**Purpose**: Get new access token using refresh token
**Auth**: None (refresh token in body)
**Request Body**:
```json
{
  "refresh_token": "jwt-refresh-token"
}
```
**Response**:
```json
{
  "access_token": "new-jwt-token"
}
```
**How It Works**: Refresh token validated against DB, new access token issued

---

#### POST `/api/auth/logout`
**Purpose**: Invalidate refresh token
**Auth**: Bearer token required
**Response**:
```json
{
  "message": "Logged out successfully"
}
```
**How It Works**: Refresh token deleted from database

---

#### GET `/api/auth/me`
**Purpose**: Get current user profile
**Auth**: Bearer token required
**Response**:
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "full_name": "John Doe",
  "is_active": true,
  "created_at": "2024-01-15T10:30:00"
}
```
**How It Works**: User ID extracted from JWT, user record fetched

---

### Processing Endpoints

#### POST `/api/process/process-single`
**Purpose**: Process single PDF document
**Auth**: Optional (Bearer token)
**Request Body**:
```json
{
  "url": "https://example.com/document.pdf",
  "languages": ["en", "es"],
  "max_tags": 10
}
```
**Response**:
```json
{
  "tags": ["technology", "innovation", ...],
  "extracted_text": "Full text content...",
  "metadata": {
    "processing_time": 2.5,
    "language_detected": "en"
  }
}
```
**How It Works**:
1. PDF downloaded from URL
2. Text extracted with PyPDF2
3. AI generates tags via Gemini
4. If authenticated, saved to DB
5. Results returned

---

#### POST `/api/process/process-batch`
**Purpose**: Start batch processing job
**Auth**: Optional
**Request Body**:
```json
{
  "spreadsheet_url": "https://example.com/list.xlsx",
  "url_column": "PDF Link",
  "languages": ["en"],
  "max_tags": 10
}
```
**Response**:
```json
{
  "job_id": "uuid",
  "status": "processing",
  "total_documents": 50
}
```
**How It Works**:
1. Spreadsheet downloaded and parsed
2. Job created in DB
3. Documents created with "pending" status
4. Background processing starts
5. Job ID returned immediately

---

#### GET `/api/process/batch-status/{job_id}`
**Purpose**: Check batch job progress
**Auth**: None
**Response**:
```json
{
  "job_id": "uuid",
  "status": "processing",
  "total": 50,
  "completed": 30,
  "failed": 2,
  "results": [...]
}
```
**How It Works**: In-memory job status fetched from AsyncBatchProcessor

---

### History Endpoints

#### GET `/api/history/jobs`
**Purpose**: List processing jobs
**Auth**: Optional (filters by user if authenticated)
**Query Params**:
- `limit`: Max results (default: 50, max: 100)
- `offset`: Pagination offset (default: 0)
- `status`: Filter by status (optional)

**Response**:
```json
{
  "jobs": [
    {
      "id": "uuid",
      "job_type": "batch",
      "status": "completed",
      "total_documents": 50,
      "processed_count": 48,
      "failed_count": 2,
      "created_at": "2024-01-15T10:30:00",
      "completed_at": "2024-01-15T10:45:00"
    }
  ],
  "total": 100,
  "limit": 50,
  "offset": 0
}
```
**How It Works**: Query `processing_jobs` table with user_id filter and pagination

---

#### GET `/api/history/jobs/{job_id}`
**Purpose**: Get job details with all documents
**Auth**: Optional (ownership check if authenticated)
**Response**:
```json
{
  "id": "uuid",
  "job_type": "batch",
  "status": "completed",
  "total_documents": 50,
  "processed_count": 48,
  "failed_count": 2,
  "config": {...},
  "documents": [
    {
      "id": "uuid",
      "title": "document.pdf",
      "status": "success",
      "tags": ["tag1", "tag2"],
      "processed_at": "2024-01-15T10:35:00"
    }
  ]
}
```
**How It Works**: Join query on `processing_jobs` and `documents` tables

---

#### DELETE `/api/history/jobs/{job_id}`
**Purpose**: Delete job and all documents
**Auth**: Required (ownership verified)
**Response**:
```json
{
  "message": "Job deleted successfully",
  "job_id": "uuid"
}
```
**How It Works**:
1. Verify job ownership
2. CASCADE delete removes documents
3. MinIO files remain (cleanup task needed)

---

#### GET `/api/history/documents`
**Purpose**: List recent documents
**Auth**: Optional (filters by user if authenticated)
**Query Params**:
- `limit`: Max results (default: 50)

**Response**:
```json
{
  "documents": [
    {
      "id": "uuid",
      "title": "document.pdf",
      "file_path": "https://...",
      "status": "success",
      "tags": ["tag1", "tag2"],
      "processed_at": "2024-01-15T10:35:00"
    }
  ],
  "total": 250
}
```
**How It Works**: Query `documents` table ordered by `processed_at DESC`

---

#### GET `/api/history/documents/search`
**Purpose**: Search documents by title or tags
**Auth**: Required
**Query Params**:
- `query`: Search term (required)
- `limit`: Max results (default: 50)

**Response**: Same as `/documents` endpoint
**How It Works**: ILIKE query on title and JSONB tags field

---

#### GET `/api/history/documents/{doc_id}`
**Purpose**: Get full document details
**Auth**: Optional (ownership check)
**Response**:
```json
{
  "id": "uuid",
  "job_id": "uuid",
  "title": "document.pdf",
  "file_path": "https://...",
  "file_size": 1048576,
  "mime_type": "application/pdf",
  "status": "success",
  "tags": ["tag1", "tag2", ...],
  "extracted_text": "Full text content...",
  "processing_metadata": {...},
  "error_message": null,
  "processed_at": "2024-01-15T10:35:00"
}
```
**How It Works**: Single document query by ID

---

#### GET `/api/history/stats`
**Purpose**: Get user dashboard statistics
**Auth**: Required
**Response**:
```json
{
  "total_jobs": 25,
  "total_documents": 500,
  "documents_processed": 480,
  "documents_failed": 20,
  "jobs_by_status": {
    "completed": 20,
    "failed": 3,
    "processing": 2
  },
  "recent_activity": [
    {
      "id": "uuid",
      "job_type": "batch",
      "status": "completed",
      ...
    }
  ]
}
```
**How It Works**: Aggregate query on user's jobs and documents

---

## Database Schema

### ER Diagram (Logical Relationships)

```
┌──────────────┐
│    users     │
├──────────────┤
│ id (PK)      │───┐
│ email        │   │
│ password_hash│   │
│ full_name    │   │
│ is_active    │   │
│ created_at   │   │
│ updated_at   │   │
└──────────────┘   │
                   │
                   │ 1:N
                   │
        ┌──────────┴──────────┬───────────────────┐
        │                     │                   │
        ↓                     ↓                   ↓
┌──────────────┐   ┌──────────────────┐   ┌──────────────┐
│refresh_tokens│   │ processing_jobs  │   │  documents   │
├──────────────┤   ├──────────────────┤   ├──────────────┤
│ id (PK)      │   │ id (PK)          │───│ job_id (FK)  │
│ user_id (FK) │   │ user_id (FK)     │   │ user_id (FK) │
│ token        │   │ job_type         │   │ title        │
│ expires_at   │   │ status           │   │ file_path    │
│ created_at   │   │ total_documents  │   │ status       │
└──────────────┘   │ processed_count  │   │ tags (JSONB) │
                   │ failed_count     │   │ extracted_text
                   │ config (JSONB)   │   │ processed_at │
                   │ started_at       │   │ created_at   │
                   │ completed_at     │   └──────────────┘
                   └──────────────────┘
                          1:N
                           │
                           └─────────────────────┘
```

### Schema Design Rationale

#### 1. **users** Table

**Purpose**: Store user accounts and authentication credentials

**Key Decisions**:
- **UUID Primary Key**:
  - Why: Distributed-friendly, non-sequential (security), no collision risk
  - Alternative: Auto-increment integers (sequential = enumeration risk)

- **email UNIQUE constraint**:
  - Why: Prevents duplicate accounts, used for login
  - Index: Fast email lookups during authentication

- **password_hash (not password)**:
  - Why: Never store plaintext passwords
  - bcrypt: Adaptive hashing, slow by design (prevents brute force)

- **is_active Boolean**:
  - Why: Soft delete - deactivate accounts without losing data
  - Use case: User requests account suspension

- **Timestamps**:
  - `created_at`: Account registration date
  - `updated_at`: Last profile modification (trigger maintains this)

**Indexes**:
```sql
CREATE INDEX idx_users_email ON users(email);
```
- Critical for login performance (O(1) vs O(N))

---

#### 2. **refresh_tokens** Table

**Purpose**: Track long-lived JWT refresh tokens for rotation and invalidation

**Key Decisions**:
- **Separate Table (not in users)**:
  - Why: One user can have multiple sessions (mobile + web)
  - Enables per-session logout

- **token VARCHAR(512)**:
  - Why: JWT tokens are ~300-400 chars
  - UNIQUE constraint prevents token reuse

- **expires_at Timestamp**:
  - Why: Explicit expiration for cleanup jobs
  - Prevents infinite token validity

- **CASCADE DELETE on user_id**:
  - Why: User deletion invalidates all sessions
  - Security: Deleted users can't login with old tokens

**Indexes**:
```sql
CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_expires_at ON refresh_tokens(expires_at);
```
- `user_id`: Fast session lookup
- `expires_at`: Efficient cleanup job (`DELETE WHERE expires_at < NOW()`)

**Cleanup Strategy**:
```sql
-- Cron job runs daily
DELETE FROM refresh_tokens WHERE expires_at < CURRENT_TIMESTAMP;
```

---

#### 3. **processing_jobs** Table

**Purpose**: Track batch processing operations with progress and status

**Key Decisions**:
- **user_id with SET NULL**:
  - Why: Anonymous users can process (no user_id)
  - SET NULL: User deletion doesn't cascade to jobs (data retention)

- **status VARCHAR(50)**:
  - Values: `pending`, `processing`, `completed`, `failed`, `partial`
  - Why: Enum would be rigid, VARCHAR allows new statuses

- **Counters (total_documents, processed_count, failed_count)**:
  - Why: Avoid expensive COUNT queries on documents table
  - Denormalized for performance

- **config JSONB**:
  - Why: Flexible storage for processing parameters
  - Example: `{"languages": ["en"], "max_tags": 10}`
  - JSONB (not JSON): Indexable, queryable

- **Three Timestamps**:
  - `created_at`: Job queued
  - `started_at`: Processing began
  - `completed_at`: Processing finished
  - Why: Enables analytics (queue time, processing time)

**Indexes**:
```sql
CREATE INDEX idx_jobs_user_id ON processing_jobs(user_id);
CREATE INDEX idx_jobs_status ON processing_jobs(status);
```
- `user_id`: User's job history
- `status`: Filter by active/completed jobs

**Query Example**:
```sql
-- Get user's active jobs
SELECT * FROM processing_jobs
WHERE user_id = $1 AND status IN ('pending', 'processing')
ORDER BY created_at DESC;
```

---

#### 4. **documents** Table

**Purpose**: Store individual document processing results

**Key Decisions**:
- **job_id with CASCADE DELETE**:
  - Why: Deleting job removes all documents
  - Maintains referential integrity

- **user_id with SET NULL**:
  - Why: Can belong to job or standalone (single processing)
  - SET NULL: User deletion preserves document records

- **tags JSONB (not separate table)**:
  - Why: Variable tag count, multilingual tags
  - Alternative: `tags` table with many-to-many join (slower)
  - JSONB benefits: Atomic updates, indexable, queryable

- **extracted_text TEXT**:
  - Why: Full-text search, debugging, re-processing
  - Storage cost: ~10KB per document (acceptable)

- **processing_metadata JSONB**:
  - Example: `{"language_detected": "en", "page_count": 5}`
  - Why: Extensible, no schema changes for new metadata

- **file_size BIGINT**:
  - Why: Track storage usage, quota enforcement
  - BIGINT: Supports files > 2GB

**Indexes**:
```sql
CREATE INDEX idx_documents_job_id ON documents(job_id);
CREATE INDEX idx_documents_user_id ON documents(user_id);
CREATE INDEX idx_documents_status ON documents(status);
```
- `job_id`: Get all documents in job
- `user_id`: User's document library
- `status`: Filter successful/failed docs

**JSONB Queries**:
```sql
-- Search tags
SELECT * FROM documents WHERE tags::text ILIKE '%technology%';

-- Count documents with Spanish tags
SELECT COUNT(*) FROM documents
WHERE processing_metadata->>'language_detected' = 'es';
```

---

### Schema Evolution Considerations

**Why This Schema Scales**:

1. **Partitioning Ready**:
   - `created_at` allows time-based partitioning
   - Old documents archived to separate tables

2. **Analytics Friendly**:
   - Separate jobs/documents tables enable aggregations
   - Timestamps support time-series analysis

3. **Multi-tenancy Ready**:
   - User ID on all tables
   - Can add organization_id layer later

**Future Enhancements**:
```sql
-- User quotas
ALTER TABLE users ADD COLUMN monthly_quota INTEGER DEFAULT 100;
ALTER TABLE users ADD COLUMN quota_used INTEGER DEFAULT 0;

-- Document versioning
ALTER TABLE documents ADD COLUMN version INTEGER DEFAULT 1;
ALTER TABLE documents ADD COLUMN parent_doc_id UUID REFERENCES documents(id);

-- Audit trail
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    action VARCHAR(50),
    resource_type VARCHAR(50),
    resource_id UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Technology Deep Dive

### PostgreSQL: Why and How It Works

**Why PostgreSQL**:
1. **ACID Compliance**: Guarantees data consistency
   - Atomicity: Transactions succeed/fail as unit
   - Consistency: Schema constraints enforced
   - Isolation: Concurrent transactions don't interfere
   - Durability: Committed data survives crashes

2. **JSONB Support**:
   - Binary JSON format (faster than text JSON)
   - Indexable with GIN indexes
   - Queryable with operators (`->`, `->>`, `@>`)

3. **Advanced Features**:
   - Full-text search (tsvector, tsquery)
   - Window functions for analytics
   - Common Table Expressions (CTEs) for complex queries
   - Triggers for automatic timestamp updates

**How PostgreSQL Ensures Performance**:
```sql
-- B-tree index for lookups
CREATE INDEX idx_users_email ON users(email);
-- Lookup: O(log N) instead of O(N)

-- GIN index for JSONB
CREATE INDEX idx_documents_tags ON documents USING GIN (tags);
-- Tag search: O(log N) even with large JSONB

-- Partial index for active users only
CREATE INDEX idx_active_users ON users(email) WHERE is_active = true;
-- Smaller index = faster queries
```

**Connection Pooling (asyncpg)**:
```python
# Without pooling: 10 requests = 10 connections
# With pooling: 10 requests reuse 5 connections

pool = await asyncpg.create_pool(
    min_size=5,    # Always maintain 5 connections
    max_size=20,   # Scale up to 20 under load
    max_inactive_connection_lifetime=300  # Close idle connections
)

# Request lifecycle:
# 1. Borrow connection from pool
# 2. Execute query
# 3. Return connection to pool (not closed!)
```

---

### MinIO: S3-Compatible Object Storage

**Why MinIO**:
1. **S3 Compatible**: Same API as AWS S3
   - Easy migration: Change endpoint URL, same code works
   - Industry standard: Tons of libraries and tools

2. **Self-Hosted**:
   - No AWS costs during development
   - Full control over data
   - No internet dependency

3. **Object Storage Benefits**:
   - No file system limits (inodes, path length)
   - Built-in checksums (data integrity)
   - Versioning support
   - Scalable (add more nodes)

**How MinIO Works**:
```python
from minio import Minio

client = Minio(
    "localhost:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False  # HTTPS in production
)

# Upload
client.put_object(
    bucket_name="documents",
    object_name="user123/job456/doc789.pdf",
    data=file_bytes,
    length=len(file_bytes),
    content_type="application/pdf"
)

# Download
response = client.get_object("documents", "user123/job456/doc789.pdf")
file_bytes = response.read()

# Presigned URL (temporary access)
url = client.presigned_get_object(
    bucket_name="documents",
    object_name="user123/job456/doc789.pdf",
    expires=timedelta(hours=1)
)
# URL valid for 1 hour, no auth needed
```

**Storage Structure**:
```
documents/                    # Bucket
├── anonymous/                # Anonymous user uploads
│   ├── <job_id>/
│   │   └── <doc_id>.pdf
├── <user_id>/                # Authenticated user uploads
│   ├── <job_id>/
│   │   ├── <doc_id_1>.pdf
│   │   ├── <doc_id_2>.pdf
│   │   └── ...
```

**Why This Structure**:
- **User isolation**: Each user has own folder
- **Job organization**: Easy to list all files in job
- **UUID filenames**: No collisions, unique globally

---

### JWT Authentication: How It Works

**Token Structure**:
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMTIzIiwiZW1haWwiOiJ1c2VyQGV4YW1wbGUuY29tIiwiZXhwIjoxNjMxMjQwMDAwfQ.Sv5V8W3mF1_Zg3yQp8r_N5hN4n1_N7g3qL8rNm3pQ8g

[Header].[Payload].[Signature]

Header (Base64):
{
  "alg": "HS256",
  "typ": "JWT"
}

Payload (Base64):
{
  "sub": "user-uuid",
  "email": "user@example.com",
  "exp": 1631240000,
  "type": "access"
}

Signature:
HMACSHA256(
  base64UrlEncode(header) + "." + base64UrlEncode(payload),
  SECRET_KEY
)
```

**Security Properties**:
1. **Tamper-Proof**: Changing payload invalidates signature
2. **Stateless**: No database lookup needed for verification
3. **Expiring**: `exp` claim enforces time limits

**Access vs Refresh Tokens**:
```
Access Token:
- Short-lived (30 minutes)
- Used for API requests
- Stored in memory/localStorage
- Not revocable (must expire)

Refresh Token:
- Long-lived (7 days)
- Used to get new access tokens
- Stored in database
- Revocable (logout deletes it)
```

**Security Flow**:
```python
# 1. Create access token
access_token = jwt.encode(
    {
        "sub": user_id,
        "email": user_email,
        "exp": datetime.utcnow() + timedelta(minutes=30),
        "type": "access"
    },
    SECRET_KEY,
    algorithm="HS256"
)

# 2. Verify token
try:
    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    user_id = payload["sub"]
except jwt.ExpiredSignatureError:
    raise HTTPException(401, "Token expired")
except jwt.InvalidTokenError:
    raise HTTPException(401, "Invalid token")
```

**Why This is Secure**:
- `SECRET_KEY` never sent to client
- Changing SECRET_KEY invalidates all tokens
- Signature verification prevents tampering
- Expiration prevents stolen tokens from working forever

---

### Bcrypt Password Hashing

**Why Bcrypt**:
1. **Slow by Design**: ~100ms per hash (prevents brute force)
2. **Adaptive**: Can increase work factor as CPUs get faster
3. **Salted**: Same password = different hashes

**How It Works**:
```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hash password (registration)
password = "user_password_123"
hashed = pwd_context.hash(password)
# Result: $2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYy9/S0c.3m
#         ^   ^  ^                    ^
#         |   |  |                    +-- Hash (184 bits)
#         |   |  +-- Salt (128 bits)
#         |   +-- Work factor (2^12 = 4096 rounds)
#         +-- Algorithm (bcrypt)

# Verify password (login)
is_valid = pwd_context.verify("user_password_123", hashed)
# True: Password matches
# False: Password incorrect
```

**Work Factor**:
```python
# Low work factor (fast, less secure)
hashed = bcrypt.hashpw(password, bcrypt.gensalt(rounds=10))
# ~10ms, vulnerable to modern GPUs

# Default work factor (balanced)
hashed = bcrypt.hashpw(password, bcrypt.gensalt(rounds=12))
# ~100ms, good for 2024

# High work factor (slow, very secure)
hashed = bcrypt.hashpw(password, bcrypt.gensalt(rounds=14))
# ~400ms, overkill for most apps
```

**Why 100ms is Good**:
- Legitimate login: 100ms unnoticeable
- Attacker: 100ms × 1 billion attempts = 3 years

---

### Zustand State Management

**Why Zustand over Redux**:
```typescript
// Redux: Lots of boilerplate
const initialState = { user: null }
const reducer = (state, action) => { ... }
const store = createStore(reducer)
const mapStateToProps = (state) => ({ user: state.user })
const mapDispatchToProps = { login }
export default connect(mapStateToProps, mapDispatchToProps)(Component)

// Zustand: Minimal boilerplate
const useAuthStore = create((set) => ({
  user: null,
  login: async (email, password) => {
    const user = await api.login(email, password)
    set({ user })
  }
}))

function Component() {
  const { user, login } = useAuthStore()
  // Use directly!
}
```

**How Zustand Works**:
```typescript
// 1. Create store
const useStore = create<State>((set, get) => ({
  count: 0,
  increment: () => set({ count: get().count + 1 })
}))

// 2. Subscribe to specific state
function Counter() {
  const count = useStore(state => state.count)  // Only re-renders when count changes
  const increment = useStore(state => state.increment)  // Never re-renders

  return <button onClick={increment}>{count}</button>
}

// 3. Persistence middleware
const useStore = create(
  persist(
    (set) => ({ user: null }),
    { name: 'auth-storage' }  // localStorage key
  )
)
```

**Performance Optimization**:
```typescript
// Bad: Component re-renders on any state change
const { user, tokens, isAuthenticated } = useAuthStore()

// Good: Component only re-renders when user changes
const user = useAuthStore(state => state.user)
```

---

### React Server Components (Next.js 14)

**Why Next.js 14**:
1. **App Router**: File-based routing with layouts
2. **Server Components**: Faster initial load
3. **API Routes**: Backend + frontend in one repo
4. **Image Optimization**: Automatic lazy loading
5. **TypeScript**: First-class support

**Server vs Client Components**:
```typescript
// Server Component (default in app directory)
// - Runs on server
// - No JavaScript sent to browser
// - Can't use hooks (useState, useEffect)
// - Can access database directly
async function ServerComponent() {
  const data = await fetch('https://api.example.com/data')  // Runs on server
  return <div>{data.title}</div>
}

// Client Component (use 'use client' directive)
// - Runs in browser
// - Can use hooks
// - Interactive (onClick, onChange)
'use client'
function ClientComponent() {
  const [count, setCount] = useState(0)
  return <button onClick={() => setCount(count + 1)}>{count}</button>
}
```

**When to Use Each**:
- **Server**: Static content, data fetching, SEO
- **Client**: Interactivity, browser APIs, state management

---

## AWS Deployment Guide

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        AWS Cloud                             │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Application Load Balancer                │  │
│  │         (SSL Termination, HTTPS → HTTP)              │  │
│  └────────────────┬─────────────────────────────────────┘  │
│                   │                                          │
│         ┌─────────┴─────────┐                               │
│         ↓                   ↓                               │
│  ┌──────────────┐    ┌──────────────┐                      │
│  │   ECS Task   │    │   ECS Task   │                      │
│  │  (Frontend)  │    │  (Backend)   │                      │
│  │              │    │              │                      │
│  │  Next.js     │    │  FastAPI     │                      │
│  │  Port 3000   │    │  Port 8000   │                      │
│  └──────────────┘    └──────┬───────┘                      │
│                             │                               │
│                    ┌────────┴────────┐                      │
│                    ↓                 ↓                       │
│            ┌──────────────┐  ┌──────────────┐              │
│            │  RDS (Postgres)  │  S3 Bucket    │              │
│            │  Multi-AZ      │  │  (Documents)  │              │
│            └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────┘
```

### Step-by-Step Deployment

#### 1. **Database Setup (RDS)**

```bash
# Create PostgreSQL RDS instance
aws rds create-db-instance \
  --db-instance-identifier metadata-tagger-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --engine-version 15.3 \
  --master-username postgres \
  --master-user-password YOUR_SECURE_PASSWORD \
  --allocated-storage 20 \
  --storage-type gp3 \
  --vpc-security-group-ids sg-xxxxx \
  --db-subnet-group-name default \
  --multi-az \
  --backup-retention-period 7 \
  --publicly-accessible false
```

**Why Multi-AZ**:
- Automatic failover to standby
- ~99.95% availability
- Synchronous replication

**Run Schema Migration**:
```bash
# Connect from bastion host or ECS task
psql -h metadata-tagger-db.xxxxx.us-east-1.rds.amazonaws.com \
     -U postgres -d metadata_tagger \
     -f backend/app/database/schema.sql
```

---

#### 2. **Object Storage (S3)**

```bash
# Create S3 bucket
aws s3api create-bucket \
  --bucket metadata-tagger-documents \
  --region us-east-1

# Enable versioning (data protection)
aws s3api put-bucket-versioning \
  --bucket metadata-tagger-documents \
  --versioning-configuration Status=Enabled

# Set lifecycle policy (auto-delete old versions after 30 days)
aws s3api put-bucket-lifecycle-configuration \
  --bucket metadata-tagger-documents \
  --lifecycle-configuration '{
    "Rules": [{
      "Id": "DeleteOldVersions",
      "Status": "Enabled",
      "NoncurrentVersionExpiration": { "NoncurrentDays": 30 }
    }]
  }'

# Enable encryption at rest
aws s3api put-bucket-encryption \
  --bucket metadata-tagger-documents \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'
```

**Why S3 over MinIO in Production**:
- 99.999999999% durability
- Automatic scaling
- Built-in CDN (CloudFront) integration
- Pay only for usage

---

#### 3. **Container Images (ECR)**

```bash
# Create ECR repositories
aws ecr create-repository --repository-name metadata-tagger-frontend
aws ecr create-repository --repository-name metadata-tagger-backend

# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  123456789012.dkr.ecr.us-east-1.amazonaws.com

# Build and push frontend
docker build -t metadata-tagger-frontend ./frontend
docker tag metadata-tagger-frontend:latest \
  123456789012.dkr.ecr.us-east-1.amazonaws.com/metadata-tagger-frontend:latest
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/metadata-tagger-frontend:latest

# Build and push backend
docker build -t metadata-tagger-backend ./backend
docker tag metadata-tagger-backend:latest \
  123456789012.dkr.ecr.us-east-1.amazonaws.com/metadata-tagger-backend:latest
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/metadata-tagger-backend:latest
```

---

#### 4. **ECS Cluster & Task Definitions**

**Create Cluster**:
```bash
aws ecs create-cluster --cluster-name metadata-tagger-cluster
```

**Task Definition (Backend)**:
```json
{
  "family": "metadata-tagger-backend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "backend",
      "image": "123456789012.dkr.ecr.us-east-1.amazonaws.com/metadata-tagger-backend:latest",
      "portMappings": [
        { "containerPort": 8000, "protocol": "tcp" }
      ],
      "environment": [
        { "name": "DATABASE_HOST", "value": "metadata-tagger-db.xxxxx.rds.amazonaws.com" },
        { "name": "DATABASE_NAME", "value": "metadata_tagger" },
        { "name": "DATABASE_USER", "value": "postgres" },
        { "name": "MINIO_ENDPOINT", "value": "s3.amazonaws.com" },
        { "name": "MINIO_BUCKET", "value": "metadata-tagger-documents" }
      ],
      "secrets": [
        { "name": "DATABASE_PASSWORD", "valueFrom": "arn:aws:secretsmanager:..." },
        { "name": "SECRET_KEY", "valueFrom": "arn:aws:secretsmanager:..." },
        { "name": "AWS_ACCESS_KEY_ID", "valueFrom": "arn:aws:secretsmanager:..." },
        { "name": "AWS_SECRET_ACCESS_KEY", "valueFrom": "arn:aws:secretsmanager:..." }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/metadata-tagger-backend",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

**Task Definition (Frontend)**:
```json
{
  "family": "metadata-tagger-frontend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "containerDefinitions": [
    {
      "name": "frontend",
      "image": "123456789012.dkr.ecr.us-east-1.amazonaws.com/metadata-tagger-frontend:latest",
      "portMappings": [
        { "containerPort": 3000, "protocol": "tcp" }
      ],
      "environment": [
        { "name": "NEXT_PUBLIC_API_URL", "value": "https://api.yourdomain.com" }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/metadata-tagger-frontend",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

**Register Task Definitions**:
```bash
aws ecs register-task-definition --cli-input-json file://backend-task.json
aws ecs register-task-definition --cli-input-json file://frontend-task.json
```

---

#### 5. **Application Load Balancer**

```bash
# Create ALB
aws elbv2 create-load-balancer \
  --name metadata-tagger-alb \
  --subnets subnet-xxxxx subnet-yyyyy \
  --security-groups sg-xxxxx \
  --scheme internet-facing \
  --type application

# Create target groups
aws elbv2 create-target-group \
  --name backend-tg \
  --protocol HTTP \
  --port 8000 \
  --vpc-id vpc-xxxxx \
  --target-type ip \
  --health-check-path /health

aws elbv2 create-target-group \
  --name frontend-tg \
  --protocol HTTP \
  --port 3000 \
  --vpc-id vpc-xxxxx \
  --target-type ip \
  --health-check-path /

# Create HTTPS listener (requires SSL certificate from ACM)
aws elbv2 create-listener \
  --load-balancer-arn arn:aws:elasticloadbalancing:... \
  --protocol HTTPS \
  --port 443 \
  --certificates CertificateArn=arn:aws:acm:... \
  --default-actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:.../frontend-tg

# Add rule for backend routing
aws elbv2 create-rule \
  --listener-arn arn:aws:elasticloadbalancing:... \
  --priority 10 \
  --conditions Field=path-pattern,Values='/api/*' \
  --actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:.../backend-tg
```

---

#### 6. **ECS Services**

```bash
# Create backend service
aws ecs create-service \
  --cluster metadata-tagger-cluster \
  --service-name backend-service \
  --task-definition metadata-tagger-backend \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration '{
    "awsvpcConfiguration": {
      "subnets": ["subnet-xxxxx", "subnet-yyyyy"],
      "securityGroups": ["sg-xxxxx"],
      "assignPublicIp": "ENABLED"
    }
  }' \
  --load-balancers '[{
    "targetGroupArn": "arn:aws:elasticloadbalancing:.../backend-tg",
    "containerName": "backend",
    "containerPort": 8000
  }]'

# Create frontend service
aws ecs create-service \
  --cluster metadata-tagger-cluster \
  --service-name frontend-service \
  --task-definition metadata-tagger-frontend \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration '{
    "awsvpcConfiguration": {
      "subnets": ["subnet-xxxxx", "subnet-yyyyy"],
      "securityGroups": ["sg-xxxxx"],
      "assignPublicIp": "ENABLED"
    }
  }' \
  --load-balancers '[{
    "targetGroupArn": "arn:aws:elasticloadbalancing:.../frontend-tg",
    "containerName": "frontend",
    "containerPort": 3000
  }]'
```

---

#### 7. **Auto Scaling**

```bash
# Register scalable target
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/metadata-tagger-cluster/backend-service \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 2 \
  --max-capacity 10

# Create scaling policy (CPU-based)
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --resource-id service/metadata-tagger-cluster/backend-service \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-name cpu-scaling \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 70.0,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
    },
    "ScaleInCooldown": 60,
    "ScaleOutCooldown": 60
  }'
```

---

#### 8. **DNS & SSL (Route 53 + ACM)**

```bash
# Request SSL certificate
aws acm request-certificate \
  --domain-name yourdomain.com \
  --subject-alternative-names '*.yourdomain.com' \
  --validation-method DNS

# Create Route 53 record for ALB
aws route53 change-resource-record-sets \
  --hosted-zone-id Z123456789 \
  --change-batch '{
    "Changes": [{
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "app.yourdomain.com",
        "Type": "A",
        "AliasTarget": {
          "HostedZoneId": "Z1234567890ABC",
          "DNSName": "metadata-tagger-alb-123456789.us-east-1.elb.amazonaws.com",
          "EvaluateTargetHealth": true
        }
      }
    }]
  }'
```

---

### Cost Estimation (Monthly)

```
ECS Fargate:
- Backend: 2 tasks × 0.5 vCPU × $0.04 × 720 hours = $28.80
- Frontend: 2 tasks × 0.25 vCPU × $0.04 × 720 hours = $14.40

RDS:
- db.t3.micro Multi-AZ = $25

S3:
- 100GB storage = $2.30
- 10,000 PUT requests = $0.05
- 100,000 GET requests = $0.04

ALB:
- Load balancer hours = $16.20
- LCUs (minimal traffic) = $5

Total: ~$92/month (for light usage)
```

**Cost Optimization**:
- Use Fargate Spot for non-critical tasks (-70% cost)
- S3 Intelligent-Tiering for old documents
- RDS Reserved Instances (-40% cost with 1-year commitment)

---

### Monitoring & Alerts

```bash
# CloudWatch alarms
aws cloudwatch put-metric-alarm \
  --alarm-name high-cpu-backend \
  --alarm-description "Backend CPU > 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/ECS \
  --statistic Average \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=ServiceName,Value=backend-service \
  --alarm-actions arn:aws:sns:us-east-1:123456789012:admin-alerts

# Log aggregation with CloudWatch Insights
aws logs start-query \
  --log-group-name /ecs/metadata-tagger-backend \
  --start-time $(date -d '1 hour ago' +%s) \
  --end-time $(date +%s) \
  --query-string 'fields @timestamp, @message | filter @message like /ERROR/ | sort @timestamp desc'
```

---

### CI/CD Pipeline (GitHub Actions)

```yaml
name: Deploy to AWS

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v1

      - name: Build and push backend
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
        run: |
          docker build -t $ECR_REGISTRY/metadata-tagger-backend:latest ./backend
          docker push $ECR_REGISTRY/metadata-tagger-backend:latest

      - name: Build and push frontend
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
        run: |
          docker build -t $ECR_REGISTRY/metadata-tagger-frontend:latest ./frontend
          docker push $ECR_REGISTRY/metadata-tagger-frontend:latest

      - name: Update ECS services
        run: |
          aws ecs update-service --cluster metadata-tagger-cluster \
            --service backend-service --force-new-deployment
          aws ecs update-service --cluster metadata-tagger-cluster \
            --service frontend-service --force-new-deployment
```

---

## Summary

This phase transformed the application from a stateless tool into a production-ready multi-user platform:

**What Changed**:
- ✅ User authentication with JWT
- ✅ Persistent data storage (PostgreSQL + S3)
- ✅ Full-stack user interface
- ✅ Job history and search
- ✅ Multi-user isolation

**Technologies Mastered**:
- PostgreSQL async connections and JSONB
- JWT authentication flow
- Bcrypt password hashing
- MinIO/S3 object storage
- Zustand state management
- Next.js 14 App Router
- Protected routes and auth interceptors

**Production Ready**:
- Horizontal scaling (ECS auto-scaling)
- High availability (Multi-AZ RDS, ALB)
- Secure (HTTPS, encrypted storage, hashed passwords)
- Observable (CloudWatch logs and metrics)

**Next Steps**:
- Email verification on registration
- Password reset flow
- Rate limiting per user
- Admin dashboard
- Usage quotas and billing
