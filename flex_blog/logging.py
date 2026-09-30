import logging
from django.conf import settings

# Configure the logger
logger = logging.getLogger('flex_blog')

def configure_logging():
    """Configure logging based on settings."""
    from flex_blog.conf import settings as blog_settings
    
    if not logger.handlers:
        level = getattr(logging, blog_settings.LOGGING.get('level', 'INFO'))
        logger.setLevel(level)
        
        # Add handlers based on settings
        handlers = blog_settings.LOGGING.get('handlers', ['console'])
        
        if 'console' in handlers:
            console = logging.StreamHandler()
            console.setLevel(level)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console.setFormatter(formatter)
            logger.addHandler(console)
            
        if 'file' in handlers:
            file_handler = logging.FileHandler(blog_settings.LOGGING.get('file_path', 'flex_blog.log'))
            file_handler.setLevel(level)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    return logger

# Initialize the logger
logger = configure_logging()