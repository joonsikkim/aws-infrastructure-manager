#!/bin/bash
# Deployment script for AWS Infrastructure Manager

set -e

# Default values
ENV="development"
BUILD_FRONTEND=true
BUILD_BACKEND=true
PUSH_IMAGES=false
TAG="latest"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --env|-e)
      ENV="$2"
      shift 2
      ;;
    --tag|-t)
      TAG="$2"
      shift 2
      ;;
    --skip-frontend)
      BUILD_FRONTEND=false
      shift
      ;;
    --skip-backend)
      BUILD_BACKEND=false
      shift
      ;;
    --push)
      PUSH_IMAGES=true
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --env, -e ENV       Deployment environment (development, testing, staging, production)"
      echo "  --tag, -t TAG       Docker image tag (default: latest)"
      echo "  --skip-frontend     Skip building frontend"
      echo "  --skip-backend      Skip building backend"
      echo "  --push              Push Docker images to registry"
      echo "  --help, -h          Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Validate environment
if [[ ! "$ENV" =~ ^(development|testing|staging|production)$ ]]; then
  echo "Invalid environment: $ENV"
  echo "Valid environments: development, testing, staging, production"
  exit 1
fi

echo "Deploying AWS Infrastructure Manager to $ENV environment with tag $TAG"

# Set environment-specific variables
case $ENV in
  development)
    DOCKER_COMPOSE_FILE="docker-compose.yml"
    ;;
  testing)
    DOCKER_COMPOSE_FILE="docker-compose.test.yml"
    ;;
  staging)
    DOCKER_COMPOSE_FILE="docker-compose.staging.yml"
    ;;
  production)
    DOCKER_COMPOSE_FILE="docker-compose.prod.yml"
    ;;
esac

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
  echo "Docker is not installed. Please install Docker first."
  exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
  echo "Docker Compose is not installed. Please install Docker Compose first."
  exit 1
fi

# Build backend
if [ "$BUILD_BACKEND" = true ]; then
  echo "Building backend Docker image..."
  docker build -t aws-infrastructure-manager:$TAG \
    --build-arg ENV=$ENV \
    .
  
  if [ "$PUSH_IMAGES" = true ]; then
    echo "Pushing backend Docker image..."
    # Replace with your Docker registry
    docker tag aws-infrastructure-manager:$TAG your-registry/aws-infrastructure-manager:$TAG
    docker push your-registry/aws-infrastructure-manager:$TAG
  fi
fi

# Build frontend
if [ "$BUILD_FRONTEND" = true ]; then
  echo "Building frontend Docker image..."
  docker build -t aws-infrastructure-manager-frontend:$TAG \
    --build-arg ENV=$ENV \
    ./frontend
  
  if [ "$PUSH_IMAGES" = true ]; then
    echo "Pushing frontend Docker image..."
    # Replace with your Docker registry
    docker tag aws-infrastructure-manager-frontend:$TAG your-registry/aws-infrastructure-manager-frontend:$TAG
    docker push your-registry/aws-infrastructure-manager-frontend:$TAG
  fi
fi

# Deploy using Docker Compose
if [ -f "$DOCKER_COMPOSE_FILE" ]; then
  echo "Deploying with Docker Compose using $DOCKER_COMPOSE_FILE..."
  docker-compose -f $DOCKER_COMPOSE_FILE up -d
else
  echo "Docker Compose file $DOCKER_COMPOSE_FILE not found."
  exit 1
fi

echo "Deployment completed successfully!"