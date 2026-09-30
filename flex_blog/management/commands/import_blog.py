from django.core.management.base import BaseCommand
from django.utils.translation import gettext_lazy as _
from flex_blog.registry import model_registry
from django.utils.text import slugify
from flex_blog.utils import generate_unique_slug
import json
import os
import logging
from django.db import transaction
from django.core.files.base import ContentFile
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = _('Import blog content from JSON files')
    
    def add_arguments(self, parser):
        parser.add_argument(
            'input_dir',
            help=_('Directory containing JSON files to import')
        )
        parser.add_argument(
            '--models',
            nargs='+',
            default=['author', 'category', 'tag', 'article', 'comment'],
            help=_('Models to import (default: all, in order)')
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help=_('Clear existing data before import')
        )
    
    def handle(self, *args, **options):
        """Handle the command execution."""
        input_dir = options['input_dir']
        models_to_import = options['models']
        clear = options['clear']
        
        # Validate input directory
        if not os.path.isdir(input_dir):
            self.stdout.write(self.style.ERROR(
                _('Input directory {0} does not exist.').format(input_dir)
            ))
            return
            
        # Import each model
        for model_name in models_to_import:
            try:
                # Get model from registry
                model = model_registry.get_model(model_name)
                if not model:
                    self.stdout.write(self.style.WARNING(
                        _('Model {0} not found in registry.').format(model_name)
                    ))
                    continue
                
                # Check if file exists
                file_path = os.path.join(input_dir, f"{model_name}.json")
                if not os.path.exists(file_path):
                    self.stdout.write(self.style.WARNING(
                        _('File {0} not found.').format(file_path)
                    ))
                    continue
                
                # Clear existing data if requested
                if clear:
                    with transaction.atomic():
                        model.objects.all().delete()
                        self.stdout.write(self.style.SUCCESS(
                            _('Cleared existing {0} data.').format(model_name)
                        ))
                
                # Import data
                self._import_model(model, model_name, file_path)
                
            except Exception as e:
                logger.error(f'Error importing {model_name}: {e}')
                self.stdout.write(self.style.ERROR(
                    _('Error importing {0}: {1}').format(model_name, str(e))
                ))
                
        # Report success
        self.stdout.write(self.style.SUCCESS(
            _('Import completed.')
        ))
    
    def _import_model(self, model, model_name, file_path):
        """Import data for a model from a JSON file."""
        # Read JSON file
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Import objects
        imported_count = 0
        skipped_count = 0
        
        with transaction.atomic():
            for item in data:
                # Handle different models
                if model_name == 'article':
                    imported = self._import_article(model, item)
                elif model_name == 'author':
                    imported = self._import_author(model, item)
                elif model_name == 'category':
                    imported = self._import_category(model, item)
                elif model_name == 'tag':
                    imported = self._import_tag(model, item)
                elif model_name == 'comment':
                    imported = self._import_comment(model, item)
                else:
                    imported = self._import_generic(model, item)
                    
                if imported:
                    imported_count += 1
                else:
                    skipped_count += 1
                    
        self.stdout.write(self.style.SUCCESS(
            _('Imported {0} {1} objects, skipped {2}.').format(
                imported_count, model_name, skipped_count
            )
        ))
    
    def _import_generic(self, model, item):
        """Import a generic model object."""
        # Create or update object
        pk = item.pop('id', None)
        
        if pk:
            # Try to find existing object
            try:
                obj = model.objects.get(pk=pk)
                
                # Update fields
                for key, value in item.items():
                    setattr(obj, key, value)
                    
                obj.save()
                return True
                
            except model.DoesNotExist:
                # Create new object
                obj = model.objects.create(id=pk, **item)
                return True
        else:
            # Create new object without specific ID
            obj = model.objects.create(**item)
            return True
    
    def _import_article(self, model, item):
        """Import an article."""
        # Handle relations
        author_id = item.pop('author', None)
        categories = item.pop('categories', [])
        tags = item.pop('tags', [])
        
        # Get or create slug
        if 'slug' not in item or not item['slug']:
            item['slug'] = generate_unique_slug(model(), item.get('title', 'article'))
            
        # Create or update article
        pk = item.pop('id', None)
        
        try:
            if pk:
                # Update existing article
                article = model.objects.get(pk=pk)
                
                # Update fields
                for key, value in item.items():
                    setattr(article, key, value)
            else:
                # Create new article
                article = model(**item)
                
            # Set author if provided
            if author_id:
                Author = model_registry.get_model('author')
                try:
                    author = Author.objects.get(pk=author_id)
                    article.author = author
                except Author.DoesNotExist:
                    pass
                    
            article.save()
            
            # Set categories
            if categories:
                Category = model_registry.get_model('category')
                for cat_id in categories:
                    try:
                        category = Category.objects.get(pk=cat_id)
                        article.categories.add(category)
                    except Category.DoesNotExist:
                        pass
                        
            # Set tags
            if tags:
                Tag = model_registry.get_model('tag')
                for tag_id in tags:
                    try:
                        tag = Tag.objects.get(pk=tag_id)
                        article.tags.add(tag)
                    except Tag.DoesNotExist:
                        pass
                        
            return True
            
        except Exception as e:
            logger.error(f'Error importing article: {e}')
            return False
    
    def _import_author(self, model, item):
        """Import an author."""
        # Handle user relationship
        user_id = item.pop('user', None)
        
        # Create or update author
        pk = item.pop('id', None)
        
        try:
            if pk:
                # Update existing author
                author = model.objects.get(pk=pk)
                
                # Update fields
                for key, value in item.items():
                    setattr(author, key, value)
            else:
                # Create new author
                author = model(**item)
                
            # Set user if provided
            if user_id:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                try:
                    user = User.objects.get(pk=user_id)
                    author.user = user
                except User.DoesNotExist:
                    pass
                    
            author.save()
            return True
            
        except Exception as e:
            logger.error(f'Error importing author: {e}')
            return False
    
    def _import_category(self, model, item):
        """Import a category."""
        # Handle parent relationship
        parent_id = item.pop('parent', None)
        
        # Get or create slug
        if 'slug' not in item or not item['slug']:
            item['slug'] = generate_unique_slug(model(), item.get('name', 'category'))
            
        # Create or update category
        pk = item.pop('id', None)
        
        try:
            if pk:
                # Update existing category
                category = model.objects.get(pk=pk)
                
                # Update fields
                for key, value in item.items():
                    setattr(category, key, value)
            else:
                # Create new category
                category = model(**item)
                
            # Save first without parent to avoid circular references
            category.save()
            
            # Set parent if provided
            if parent_id:
                try:
                    parent = model.objects.get(pk=parent_id)
                    category.parent = parent
                    category.save()
                except model.DoesNotExist:
                    pass
                    
            return True
            
        except Exception as e:
            logger.error(f'Error importing category: {e}')
            return False
    
    def _import_tag(self, model, item):
        """Import a tag."""
        # Get or create slug
        if 'slug' not in item or not item['slug']:
            item['slug'] = generate_unique_slug(model(), item.get('name', 'tag'))
            
        # Create or update tag
        pk = item.pop('id', None)
        
        try:
            if pk:
                # Update existing tag
                tag = model.objects.get(pk=pk)
                
                # Update fields
                for key, value in item.items():
                    setattr(tag, key, value)
                    
                tag.save()
            else:
                # Create new tag
                tag = model.objects.create(**item)
                
            return True
            
        except Exception as e:
            logger.error(f'Error importing tag: {e}')
            return False
    
    def _import_comment(self, model, item):
        """Import a comment."""
        # Handle relations
        article_id = item.pop('article', None)
        user_id = item.pop('user', None)
        parent_id = item.pop('parent', None)
        
        # Create or update comment
        pk = item.pop('id', None)
        
        try:
            if pk:
                # Update existing comment
                comment = model.objects.get(pk=pk)
                
                # Update fields
                for key, value in item.items():
                    setattr(comment, key, value)
            else:
                # Create new comment
                comment = model(**item)
                
            # Set article if provided
            if article_id:
                Article = model_registry.get_model('article')
                try:
                    article = Article.objects.get(pk=article_id)
                    comment.article = article
                except Article.DoesNotExist:
                    return False  # Skip if article doesn't exist
                    
            # Set user if provided
            if user_id:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                try:
                    user = User.objects.get(pk=user_id)
                    comment.user = user
                except User.DoesNotExist:
                    pass
                    
            # Save first without parent to avoid circular references
            comment.save()
            
            # Set parent if provided
            if parent_id:
                try:
                    parent = model.objects.get(pk=parent_id)
                    comment.parent = parent
                    comment.save()
                except model.DoesNotExist:
                    pass
                    
            return True
            
        except Exception as e:
            logger.error(f'Error importing comment: {e}')
            return False