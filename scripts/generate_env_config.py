#!/usr/bin/env python3
"""
Script to generate environment-specific configuration files.
"""
import os
import sys
import argparse
import secrets
import string
from pathlib import Path


def generate_secret_key(length=50):
    """Generate a secure random secret key."""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def create_env_file(env_type, output_path=None):
    """Create environment-specific .env file."""
    # Base configuration
    base_config = {
        "APP_NAME": "AWS Infrastructure Manager",
        "APP_VERSION": "0.1.0",
        "ENVIRONMENT": env_type,
    }
    
    # Environment-specific configurations
    env_configs = {
        "development": {
            "API_HOST": "0.0.0.0",
            "API_PORT": "8000",
            "API_DEBUG": "true",
            "API_RELOAD": "true",
            "API_WORKERS": "1",
            "CORS_ORIGINS": "http://localhost:3000,http://localhost:8080",
            "DATABASE_URL": "sqlite:///./aws_infra_manager.db",
            "DATABASE_ECHO": "true",
            "AWS_DEFAULT_REGION": "us-east-1",
            "AWS_STATE_BUCKET": "aws-infra-manager-state-dev",
            "AWS_STATE_BUCKET_PREFIX": "projects",
            "AWS_MCP_SERVER_URL": "http://localhost:8080",
            "SECRET_KEY": generate_secret_key(),
            "LOG_LEVEL": "DEBUG",
            "LOG_FORMAT": "text",
        },
        "testing": {
            "API_HOST": "0.0.0.0",
            "API_PORT": "8000",
            "API_DEBUG": "false",
            "API_RELOAD": "false",
            "API_WORKERS": "1",
            "CORS_ORIGINS": "http://localhost:3000,http://localhost:8080",
            "DATABASE_URL": "sqlite:///:memory:",
            "DATABASE_ECHO": "false",
            "AWS_DEFAULT_REGION": "us-east-1",
            "AWS_STATE_BUCKET": "aws-infra-manager-state-test",
            "AWS_STATE_BUCKET_PREFIX": "projects",
            "AWS_MCP_SERVER_URL": "http://localhost:8080",
            "SECRET_KEY": "test-secret-key-for-testing-only-32-chars",
            "LOG_LEVEL": "WARNING",
            "LOG_FORMAT": "json",
        },
        "staging": {
            "API_HOST": "0.0.0.0",
            "API_PORT": "8000",
            "API_DEBUG": "false",
            "API_RELOAD": "false",
            "API_WORKERS": "2",
            "CORS_ORIGINS": "https://staging.example.com,https://api-staging.example.com",
            "DATABASE_URL": "postgresql://user:password@db:5432/aws_infra_manager",
            "DATABASE_ECHO": "false",
            "AWS_DEFAULT_REGION": "us-east-1",
            "AWS_STATE_BUCKET": "aws-infra-manager-state-staging",
            "AWS_STATE_BUCKET_PREFIX": "projects",
            "AWS_MCP_SERVER_URL": "http://mcp-server:8080",
            "SECRET_KEY": generate_secret_key(),
            "LOG_LEVEL": "INFO",
            "LOG_FORMAT": "json",
        },
        "production": {
            "API_HOST": "0.0.0.0",
            "API_PORT": "8000",
            "API_DEBUG": "false",
            "API_RELOAD": "false",
            "API_WORKERS": "4",
            "CORS_ORIGINS": "https://app.example.com,https://api.example.com",
            "DATABASE_URL": "postgresql://user:password@db:5432/aws_infra_manager",
            "DATABASE_ECHO": "false",
            "AWS_DEFAULT_REGION": "us-east-1",
            "AWS_STATE_BUCKET": "aws-infra-manager-state-prod",
            "AWS_STATE_BUCKET_PREFIX": "projects",
            "AWS_MCP_SERVER_URL": "http://mcp-server:8080",
            "SECRET_KEY": generate_secret_key(),
            "LOG_LEVEL": "INFO",
            "LOG_FORMAT": "json",
        }
    }
    
    if env_type not in env_configs:
        print(f"Error: Unknown environment '{env_type}'")
        print(f"Valid environments: {', '.join(env_configs.keys())}")
        sys.exit(1)
    
    # Combine base and environment-specific configs
    config = {**base_config, **env_configs[env_type]}
    
    # Determine output path
    if output_path is None:
        output_path = f".env.{env_type}"
    
    # Write to file
    with open(output_path, "w") as f:
        f.write(f"# {env_type.capitalize()} Environment Configuration\n")
        f.write(f"# Generated on {os.popen('date').read().strip()}\n\n")
        
        # Write configuration variables
        for key, value in config.items():
            f.write(f"{key}=\"{value}\"\n")
    
    print(f"Generated {env_type} environment configuration at {output_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate environment-specific configuration files")
    parser.add_argument(
        "--env",
        "-e",
        choices=["development", "testing", "staging", "production", "all"],
        default="development",
        help="Environment to generate configuration for"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (default: .env.<environment>)"
    )
    
    args = parser.parse_args()
    
    if args.env == "all":
        for env in ["development", "testing", "staging", "production"]:
            create_env_file(env)
    else:
        create_env_file(args.env, args.output)


if __name__ == "__main__":
    main()