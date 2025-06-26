# SafeDoser Backend API

A comprehensive FastAPI backend for the SafeDoser medication management application, featuring AI-powered medical assistance, user authentication, and supplement tracking.

## 🚀 Features

- **User Authentication**: Secure JWT-based authentication with Supabase
- **Supplement Management**: CRUD operations for user supplements
- **AI Medical Assistant**: Gemini AI integration for medical guidance
- **Chat System**: Persistent chat history with context awareness
- **Image Upload**: Support for supplement and user avatar images
- **Real-time Notifications**: Supplement reminder system
- **Database Integration**: Supabase PostgreSQL with Row Level Security

## 🛠️ Tech Stack

- **Framework**: FastAPI
- **Database**: Supabase (PostgreSQL)
- **AI**: Google Gemini AI
- **Authentication**: JWT with bcrypt password hashing
- **Image Processing**: Pillow
- **Deployment**: Railway/Render/Vercel compatible

## 📋 Prerequisites

- Python 3.8+
- Supabase account and project
- Google AI Studio account (for Gemini API)

## 🔧 Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/safedoser-backend.git
   cd safedoser-backend
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your actual values
   ```

5. **Set up Supabase database:**
   - Create a new Supabase project
   - Run the SQL migration in your Supabase SQL editor
   - Update .env with your Supabase credentials

## ⚙️ Configuration

### Environment Variables

Create a `.env` file with the following variables:

```env
# Supabase Configuration
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here
SUPABASE_DB_URL=postgresql://postgres:password@db.your-project-id.supabase.co:5432/postgres

# AI Configuration
GEMINI_API_KEY=your-gemini-api-key-here

# Security
JWT_SECRET_KEY=your-super-secret-jwt-key-here

# Application Settings
ENVIRONMENT=development
PORT=8000
```

### Getting API Keys

1. **Supabase:**
   - Go to [supabase.com](https://supabase.com)
   - Create a new project
   - Get URL and keys from Settings > API

2. **Gemini AI:**
   - Go to [ai.google.dev](https://ai.google.dev)
   - Create an API key in Google AI Studio

## 🚀 Running the Application

### Development

```bash
# Run with auto-reload
uvicorn app:app --reload --host 0.0.0.0 --port 8000

# Or use the Python script
python app.py
```

### Production

```bash
# Using Gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 --timeout 120 app:app

# Or using uvicorn
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4
```

## 📚 API Documentation

Once running, visit:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Key Endpoints

#### Authentication
- `POST /auth/signup` - Create new user account
- `POST /auth/login` - Authenticate user
- `POST /auth/refresh` - Refresh access token
- `POST /auth/forgot-password` - Request password reset

#### User Profile
- `GET /user/profile` - Get current user profile
- `PUT /user/profile` - Update user profile

#### Supplements
- `GET /supplements` - Get user's supplements
- `POST /supplements` - Create new supplement
- `PUT /supplements/{id}` - Update supplement
- `DELETE /supplements/{id}` - Delete supplement

#### Chat
- `POST /chat` - Send message to AI assistant
- `GET /chat/history` - Get chat history
- `DELETE /chat/clear` - Clear chat history

#### Utilities
- `GET /health` - Health check
- `POST /upload/image` - Upload image

## 🗄️ Database Schema

The application uses the following main tables:

- **users**: User accounts and profiles
- **supplements**: User supplement data
- **chat_messages**: Chat conversation history
- **supplement_logs**: Supplement intake tracking

See the migration file for complete schema details.

## 🤖 AI Integration

The backend integrates with Google Gemini AI to provide:

- **Medical Information**: Evidence-based supplement and medication guidance
- **Drug Interactions**: Warnings about potential supplement interactions
- **Personalized Advice**: Context-aware responses based on user's supplement regimen
- **Safety Reminders**: Always recommends consulting healthcare providers

### AI Features

- Context-aware responses using user's supplement data
- Medical knowledge base with safety guidelines
- Fallback responses when AI is unavailable
- Chat history for conversation continuity

## 🔒 Security

- **JWT Authentication**: Secure token-based authentication
- **Password Hashing**: bcrypt for secure password storage
- **Row Level Security**: Supabase RLS for data isolation
- **Input Validation**: Pydantic models for request validation
- **CORS Protection**: Configurable CORS middleware

## 🚀 Deployment

### Railway (Recommended)

1. **Connect GitHub repository to Railway**
2. **Set environment variables in Railway dashboard**
3. **Deploy automatically on git push**

### Render

1. **Create new Web Service on Render**
2. **Connect GitHub repository**
3. **Set build and start commands:**
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn -w 4 -b 0.0.0.0:$PORT --timeout 120 app:app`

### Vercel

1. **Install Vercel CLI**: `npm i -g vercel`
2. **Deploy**: `vercel`
3. **Set environment variables in Vercel dashboard**

## 🧪 Testing

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest

# Run with coverage
pytest --cov=app
```

## 📝 Logging

The application logs to:
- **Console**: All environments
- **File**: Production environment (`safedoser.log`)

Log levels:
- **INFO**: General application flow
- **ERROR**: Error conditions
- **WARNING**: Warning conditions

## 🔧 Development

### Code Structure

```
backend/
├── app.py              # Main FastAPI application
├── database.py         # Database operations
├── auth.py            # Authentication logic
├── ai_service.py      # AI integration
├── models.py          # Pydantic models
├── utils.py           # Utility functions
├── requirements.txt   # Python dependencies
├── .env.example      # Environment variables template
└── README.md         # This file
```

### Adding New Features

1. **Define models** in `models.py`
2. **Add database operations** in `database.py`
3. **Create API endpoints** in `app.py`
4. **Add tests** for new functionality
5. **Update documentation**

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🆘 Support

For support and questions:
- Create an issue on GitHub
- Check the API documentation at `/docs`
- Review the logs for error details

## 🔄 Version History

- **v1.0.0**: Initial release with core functionality
  - User authentication
  - Supplement management
  - AI chat integration
  - Image upload support

---

Built with ❤️ for better medication management