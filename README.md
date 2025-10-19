# eCourts Cause List Scraper 🏛️

A modern, professional web application for scraping and downloading cause list PDFs from the Indian eCourts portal. Built with FastAPI backend and responsive frontend with real-time scraping capabilit[...]

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen.svg)

### 🎬 Preview Video
Watch a quick preview of the eCourt Scraper in action:

[▶️ Watch Preview Video on Google Drive](https://docs.google.com/videos/d/13hhkrztWHz_M8f0rHusLGld5n6frPRKs2uG8zMIh4lc/edit?usp=sharing)

## 🚀 Features

### ✨ **Real eCourts Integration**
- **Direct web scraping** from eCourts portal using Selenium WebDriver
- **Smart fallback system** when eCourts portal is unavailable
- **Timeout handling** to prevent hanging requests
- **Comprehensive error handling** for all failure scenarios

### 🎯 **User-Friendly Interface**
- **Responsive design** that works on desktop, tablet, and mobile
- **Real-time loading indicators** with progress tracking
- **Smart dropdowns** that load states, districts, court complexes, and courts
- **Fast timeout system** (5 seconds) with immediate fallback data

### 📄 **PDF Generation**
- **Professional PDF creation** using jsPDF library
- **Realistic cause list formatting** with proper court headers
- **Fallback to text files** when PDF generation fails
- **Download and preview** functionality

### 🛡️ **Robust Architecture**
- **Modern FastAPI** with lifespan event handlers
- **Comprehensive error handling** for all edge cases
- **Production-ready logging** and monitoring
- **Docker support** for easy deployment

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   FastAPI       │    │   eCourts       │
│   (Alpine.js)   │◄──►│   Backend       │◄──►│   Portal        │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   PDF           │    │   Database      │    │   Web Scraping  │
│   Generation    │    │   (Optional)    │    │   (Selenium)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Chrome browser (for web scraping)
- Git

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/sandeepchaudhar/eCourt-Scrapper.git
cd eCourt-Scrapper
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your settings
```

5. **Run the application**
```bash
python app.py
```

6. **Open in browser**
```
http://localhost:8000
```

## 🐳 Docker Deployment

### Using Docker Compose (Recommended)
```bash
docker-compose up -d
```

### Manual Docker Build
```bash
docker build -t ecourts-scraper .
docker run -p 8000:8000 ecourts-scraper
```

## 📖 Usage

### Basic Workflow

1. **Select Court Details**
   - Choose State (e.g., Maharashtra, Delhi, Karnataka)
   - Select District (loaded dynamically)
   - Pick Court Complex (loaded based on district)
   - Optionally select specific court

2. **Set Date Range**
   - From Date (cause list date)
   - To Date (for bulk downloads)

3. **Start Scraping**
   - Click "Start Scraping"
   - Watch real-time progress
   - Download generated PDF

### API Endpoints

#### Get States
```http
GET /api/states
```

#### Get Districts
```http
GET /api/districts?state_code=MH
```

#### Get Court Complexes
```http
GET /api/court_complexes?state_code=MH&district_code=MUMBAI
```

#### Direct Scraping
```http
POST /api/scrape-direct
Content-Type: application/json

{
  "state_code": "MH",
  "district_code": "MUMBAI", 
  "complex_code": "SESSIONS_COURT",
  "court_code": null,
  "date": "2024-10-20"
}
```

## 🔧 Configuration

### Environment Variables

```bash
# Application Settings
APP_NAME="eCourts Cause List Scraper"
APP_VERSION="1.0.0"
DEBUG=false
HOST="0.0.0.0"
PORT=8000

# Logging
LOG_LEVEL="INFO"
LOG_FILE="ecourts_scraper.log"

# eCourts Portal Settings
ECOURTS_BASE_URL="https://services.ecourts.gov.in/ecourtindia_v6/"
REQUEST_TIMEOUT=30
MAX_RETRIES=3

# Mock Mode (for testing)
MOCK_MODE=false
REALISTIC_MOCK_DATA=true
```

### Advanced Configuration

Edit `config.py` for advanced settings:
- Custom timeout values
- Retry strategies
- Logging configuration
- CORS settings

## 🧪 Testing

### Run All Tests
```bash
pytest
```

### Run Specific Test Categories
```bash
# Test scraper functionality
pytest tests/test_scraper.py

# Test API endpoints
pytest tests/test_api.py

# Test services
pytest tests/test_services.py
```

### Test Coverage
```bash
pytest --cov=. --cov-report=html
```

## 📁 Project Structure

```
eCourt-Scrapper/
├── 📁 scraper/                 # Web scraping logic
│   ├── ecourts_scraper.py      # Main scraper with fallbacks
│   └── real_ecourts_scraper.py # Real eCourts portal scraper
├── 📁 services/                # Business logic services
│   └── download_service.py     # Download and file management
├── 📁 models/                  # Pydantic data models
│   └── court_models.py         # Court hierarchy and request models
├── 📁 templates/               # Jinja2 HTML templates
│   ├── base.html              # Base template with common elements
│   └── index.html             # Main scraper interface
├── 📁 static/                  # Frontend assets
│   ├── css/custom.css         # Responsive styling
│   ├── js/scraper.js          # Alpine.js frontend logic
│   └── downloads/             # Generated PDF files
├── 📁 utils/                   # Utility functions
│   └── pdf_generator.py       # PDF creation utilities
├── 📁 tests/                   # Test files
│   ├── test_scraper.py        # Scraper functionality tests
│   ├── test_api.py            # API endpoint tests
│   └── test_services.py       # Service layer tests
├── 📁 docs/                    # Documentation
│   └── real_ecourts_integration.md
├── 🐍 app.py                   # Main FastAPI application
├── ⚙️ config.py                # Configuration management
├── 📋 requirements.txt         # Python dependencies
├── 🐳 docker-compose.yml       # Docker orchestration
├── 🚀 deploy.sh                # Deployment script
└── 📖 README.md                # This file
```

## 🛠️ Development

### Setting Up Development Environment

1. **Install development dependencies**
```bash
pip install -r requirements.txt
pip install pytest pytest-cov black flake8
```

2. **Run in development mode**
```bash
python app.py
# Server runs with auto-reload enabled
```

3. **Code formatting**
```bash
black .
flake8 .
```

### Adding New Features

1. **Create feature branch**
```bash
git checkout -b feature/new-feature
```

2. **Make changes and test**
```bash
pytest
```

3. **Commit and push**
```bash
git add .
git commit -m "Add new feature"
git push origin feature/new-feature
```

## 🚀 Deployment

### Production Deployment

1. **Using the deployment script**
```bash
chmod +x deploy.sh
./deploy.sh
```

2. **Manual deployment**
```bash
# Set production environment
export DEBUG=false
export LOG_LEVEL=WARNING

# Install production dependencies
pip install -r requirements.txt

# Run with production server
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4
```

### Environment-Specific Configurations

- **Development**: `.env.development`
- **Production**: `.env.production`
- **Docker**: Uses environment variables from docker-compose.yml

## 🔍 Troubleshooting

### Common Issues

#### 1. **eCourts Portal Not Accessible**
```
Error: Request timeout - eCourts portal is slow
Solution: The app automatically falls back to realistic demo data
```

#### 2. **WebDriver Issues**
```
Error: No module named 'webdriver_manager'
Solution: pip install webdriver_manager
```

#### 3. **PDF Generation Fails**
```
Error: jsPDF library not loaded
Solution: App automatically falls back to text file generation
```

#### 4. **Empty Dropdowns**
```
Error: No districts/courts loading
Solution: Check network connection, app uses fallback data
```

### Debug Mode

Enable debug mode for detailed logging:
```bash
export DEBUG=true
python app.py
```

## 🤝 Contributing

We welcome contributions! Please follow these steps:

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Make your changes**
4. **Add tests** for new functionality
5. **Ensure tests pass** (`pytest`)
6. **Commit your changes** (`git commit -m 'Add amazing feature'`)
7. **Push to the branch** (`git push origin feature/amazing-feature`)
8. **Open a Pull Request**

### Code Style Guidelines

- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add docstrings for all functions and classes
- Write tests for new features
- Keep functions small and focused

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **eCourts Portal** - Government of India's digital courts initiative
- **FastAPI** - Modern, fast web framework for building APIs
- **Alpine.js** - Lightweight JavaScript framework
- **Selenium** - Web browser automation
- **jsPDF** - Client-side PDF generation

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/Raahul-01/eCourt-Scrapper/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Raahul-01/eCourt-Scrapper/discussions)
- **Email**: [Your Email]

## 🔮 Roadmap

- [ ] **Real-time notifications** for scraping progress
- [ ] **Bulk download** for multiple courts simultaneously
- [ ] **Scheduled scraping** with cron job support
- [ ] **Database integration** for storing scraped data
- [ ] **API rate limiting** and authentication
- [ ] **Mobile app** using React Native
- [ ] **Advanced filtering** and search capabilities
- [ ] **Export formats** (Excel, CSV, JSON)

---

**Made with ❤️ for the Indian Legal System**

*This tool helps lawyers, legal professionals, and citizens access court information more efficiently.*

```
