# AWS Infrastructure Manager

A comprehensive service for managing AWS infrastructure using MCP Server.

## Features

- AWS resource management through MCP Server
- Project-based infrastructure organization
- Change plan creation and approval workflows
- S3-based state management
- Dashboard for infrastructure monitoring
- Authentication and authorization

## Requirements

- Python 3.9+
- Docker and Docker Compose
- AWS Account (for production deployment)
- PostgreSQL (for production deployment)

## Quick Start

### Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/your-org/aws-infrastructure-manager.git
   cd aws-infrastructure-manager
   ```

2. Set up environment variables:
   ```bash
   # Generate environment files for development
   python scripts/generate_env_config.py --env development
   
   # Or copy the example file and modify it
   cp .env.example .env.development
   ```

3. Start the development environment using Docker Compose:
   ```bash
   docker-compose up -d
   ```

4. Access the application:
   - API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs
   - Frontend: http://localhost:3000

### Running Tests

```bash
# Run all tests
docker-compose -f docker-compose.yml -f docker-compose.test.yml up --build --abort-on-container-exit

# Run specific tests
docker-compose run --rm api pytest tests/test_infrastructure_service.py -v
```

## Configuration

The application uses environment-specific configuration files:

- `.env.development` - Development environment
- `.env.test` - Testing environment
- `.env.staging` - Staging environment
- `.env.production` - Production environment

You can generate these files using the provided script:

```bash
python scripts/generate_env_config.py --env all
```

## Deployment

### Production Deployment

1. Set up environment variables:
   ```bash
   # Generate production environment file
   python scripts/generate_env_config.py --env production
   
   # Edit the generated file with your production settings
   nano .env.production
   ```

2. Deploy using Docker Compose:
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```

### Deployment Script

For more advanced deployment options, use the deployment script:

```bash
# Deploy to production
./scripts/deploy.sh --env production --tag v1.0.0 --push

# Deploy only backend
./scripts/deploy.sh --env production --skip-frontend

# Get help
./scripts/deploy.sh --help
```

## Project Structure

```
aws-infrastructure-manager/
├── config/                 # Configuration files
├── docs/                   # Documentation
├── examples/               # Example usage
├── frontend/               # React frontend
├── localstack/             # LocalStack initialization scripts
├── monitoring/             # Prometheus and Grafana configs
├── scripts/                # Utility scripts
├── src/                    # Source code
│   ├── api/                # API endpoints
│   ├── models/             # Data models
│   ├── services/           # Business logic
│   └── utils/              # Utility functions
└── tests/                  # Tests
```

## Monitoring

The application includes built-in monitoring with Prometheus and Grafana:

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (default credentials: admin/admin)

## License

MIT