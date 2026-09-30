from django.core.management.base import BaseCommand
from django.utils.translation import gettext_lazy as _
from flex_blog.registry import model_registry
import json
import csv
import os
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = _('Export blog content to JSON or CSV format')
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--format',
            choices=['json', 'csv'],
            default='json',
            help=_('Output format (default: json)')
        )
        parser.add_argument(
            '--output',
            default='blog_export',
            help=_('Output directory or file prefix (default: blog_export)')
        )
        parser.add_argument(
            '--models',
            nargs='+',
            default=['article', 'author', 'category', 'tag', 'comment'],
            help=_('Models to export (default: all)')
        )
    
    def handle(self, *args, **options):
        """Handle the command execution."""
        export_format = options['format']
        output = options['output']
        models_to_export = options['models']
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output) or '.', exist_ok=True)
        
        for model_name in models_to_export:
            try:
                # Get model from registry
                model = model_registry.get_model(model_name)
                if not model:
                    self.stdout.write(self.style.WARNING(
                        _('Model {0} not found in registry.').format(model_name)
                    ))
                    continue
                
                # Get all instances
                objects = model.objects.all()
                
                if export_format == 'json':
                    self._export_json(objects, model_name, output)
                else:
                    self._export_csv(objects, model_name, output)
                    
            except Exception as e:
                logger.error(f'Error exporting {model_name}: {e}')
                self.stdout.write(self.style.ERROR(
                    _('Error exporting {0}: {1}').format(model_name, str(e))
                ))
                
        # Report success
        self.stdout.write(self.style.SUCCESS(
            _('Successfully exported {0} models.').format(len(models_to_export))
        ))
    
    def _export_json(self, objects, model_name, output):
        """Export objects to JSON format."""
        data = []
        
        for obj in objects:
            # Convert model instance to dictionary
            obj_dict = self._model_to_dict(obj)
            data.append(obj_dict)
            
        # Write to file
        filename = f"{output}_{model_name}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        self.stdout.write(self.style.SUCCESS(
            _('Exported {0} {1} objects to {2}').format(
                len(data), model_name, filename
            )
        ))
    
    def _export_csv(self, objects, model_name, output):
        """Export objects to CSV format."""
        if not objects:
            self.stdout.write(self.style.WARNING(
                _('No {0} objects to export.').format(model_name)
            ))
            return
            
        # Get fields from first object
        obj = objects.first()
        obj_dict = self._model_to_dict(obj)
        fieldnames = list(obj_dict.keys())
        
        # Write to file
        filename = f"{output}_{model_name}.csv"
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for obj in objects:
                obj_dict = self._model_to_dict(obj)
                writer.writerow(obj_dict)
                
        self.stdout.write(self.style.SUCCESS(
            _('Exported {0} {1} objects to {2}').format(
                objects.count(), model_name, filename
            )
        ))
    
    def _model_to_dict(self, obj):
        """Convert a model instance to a dictionary."""
        # Start with the basic fields
        result = {}
        
        # Get all field names
        for field in obj._meta.fields:
            field_name = field.name
            
            # Skip some fields that can't be easily serialized
            if field_name in ['file', 'profile_image']:
                # Store the path instead
                value = getattr(obj, field_name)
                result[field_name] = str(value) if value else None
            else:
                # Get the value
                value = getattr(obj, field_name)
                
                # Convert dates and times to strings
                if hasattr(value, 'isoformat'):
                    value = value.isoformat()
                    
                result[field_name] = value
        
        # Handle many-to-many fields
        for field in obj._meta.many_to_many:
            values = getattr(obj, field.name).values_list('pk', flat=True)
            result[field.name] = list(values)
            
        return result