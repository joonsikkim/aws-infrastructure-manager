"""
Main entry point for AWS Infrastructure Manager.
"""
import os
import argparse
import uvicorn
from config.settings import settings
from config.environments import get_config
from config.logging import configure_logging, get_logger, get_tracer, add_metric
from aws_lambda_powertools.metrics import MetricUnit


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="AWS Infrastructure Manager")
    parser.add_argument(
        "--env", 
        "-e", 
        choices=["development", "testing", "staging", "production"],
        default=os.environ.get("ENVIRONMENT", "development"),
        help="Environment to run the application in"
    )
    parser.add_argument(
        "--config", 
        "-c", 
        help="Path to custom config file"
    )
    return parser.parse_args()


@get_tracer().capture_method
def main():
    """Main application entry point."""
    # Parse command line arguments
    args = parse_args()
    
    # Set environment variable for configuration
    os.environ["ENVIRONMENT"] = args.env
    
    # Set environment-specific .env file
    if args.env != "production":
        os.environ["DOTENV_FILE"] = f".env.{args.env}"
    
    # Configure logging
    configure_logging()
    logger = get_logger(__name__)
    
    # Load environment-specific configuration
    config = get_config(args.env)
    
    logger.info(
        "Starting AWS Infrastructure Manager",
        app_name=config.app_name,
        version=config.app_version,
        environment=config.environment
    )
    
    # Add startup metric
    add_metric(
        name="ApplicationStartup",
        value=1,
        unit=MetricUnit.Count,
        environment=config.environment,
        version=config.app_version
    )
    
    try:
        # Run the application
        uvicorn.run(
            "src.app:app",
            host=config.api.host,
            port=config.api.port,
            debug=config.api.debug,
            reload=config.api.reload,
            workers=config.api.workers if not config.api.reload else 1,
            log_level=config.logging.level.lower(),
        )
    except Exception as e:
        logger.exception("Failed to start application", error=str(e))
        add_metric(
            name="ApplicationStartupError",
            value=1,
            unit=MetricUnit.Count,
            error_type=type(e).__name__
        )
        raise


if __name__ == "__main__":
    main()