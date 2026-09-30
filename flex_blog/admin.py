from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from flex_blog.registry import model_registry
from django.utils.html import format_html
from django.urls import reverse
from mptt.admin import MPTTModelAdmin
from flex_blog.conf import settings


class ArticleAdmin(admin.ModelAdmin):
    """Admin interface for Article model."""
    
    list_display = [
        'title', 'author', 'status', 'published_at',
        'comment_count', 'views', 'is_featured'
    ]
    list_filter = ['status', 'author', 'categories', 'is_featured']
    search_fields = ['title', 'content', 'summary']
    prepopulated_fields = {'slug': ('title',)}
    date_hierarchy = 'published_at'
    readonly_fields = ['views', 'reading_time', 'created_at', 'updated_at']
    fieldsets = (
        (None, {
            'fields': ('title', 'slug', 'content', 'summary')
        }),
        (_('Metadata'), {
            'fields': ('author', 'categories', 'tags', 'featured_image')
        }),
        (_('Publication'), {
            'fields': ('status', 'published_at', 'allow_comments', 'is_featured')
        }),
        (_('SEO'), {
            'fields': ('seo_title', 'seo_description', 'seo_keywords'),
            'classes': ('collapse',)
        }),
        (_('Statistics'), {
            'fields': ('views', 'reading_time'),
            'classes': ('collapse',)
        }),
        (_('Advanced'), {
            'fields': ('extra_data', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def comment_count(self, obj):
        """Get the number of comments."""
        return obj.comment_count
    comment_count.short_description = _('Comments')
    
    def get_queryset(self, request):
        """Get the queryset for the admin view."""
        qs = super().get_queryset(request)
        qs = qs.prefetch_related('author', 'categories', 'tags')
        return qs
    
    actions = ['publish_articles', 'unpublish_articles', 'feature_articles', 'unfeature_articles']
    
    def publish_articles(self, request, queryset):
        """Publish selected articles."""
        queryset.update(status='published')
    publish_articles.short_description = _('Publish selected articles')
    
    def unpublish_articles(self, request, queryset):
        """Unpublish selected articles."""
        queryset.update(status='draft')
    unpublish_articles.short_description = _('Unpublish selected articles')
    
    def feature_articles(self, request, queryset):
        """Feature selected articles."""
        queryset.update(is_featured=True)
    feature_articles.short_description = _('Feature selected articles')
    
    def unfeature_articles(self, request, queryset):
        """Unfeature selected articles."""
        queryset.update(is_featured=False)
    unfeature_articles.short_description = _('Unfeature selected articles')


class AuthorAdmin(admin.ModelAdmin):
    """Admin interface for Author model."""
    
    list_display = ['display_name', 'user', 'article_count', 'is_active']
    list_filter = ['is_active']
    search_fields = ['display_name', 'bio', 'user__username']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        (None, {
            'fields': ('user', 'display_name', 'bio', 'profile_image')
        }),
        (_('Contact'), {
            'fields': ('website', 'social_links')
        }),
        (_('Status'), {
            'fields': ('is_active',)
        }),
        (_('Advanced'), {
            'fields': ('extra_data', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def article_count(self, obj):
        """Get the number of articles written by the author."""
        return obj.article_count
    article_count.short_description = _('Articles')


class CategoryAdmin(MPTTModelAdmin):
    """Admin interface for Category model."""
    
    list_display = ['name', 'parent', 'article_count', 'order', 'is_active']
    list_filter = ['is_active', 'parent']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at']
    mptt_level_indent = 20
    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'description', 'parent')
        }),
        (_('Display'), {
            'fields': ('order', 'icon')
        }),
        (_('Status'), {
            'fields': ('is_active',)
        }),
        (_('Advanced'), {
            'fields': ('extra_data', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def article_count(self, obj):
        """Get the number of articles in the category."""
        return obj.article_count
    article_count.short_description = _('Articles')


class TagAdmin(admin.ModelAdmin):
    """Admin interface for Tag model."""
    
    list_display = ['name', 'article_count', 'color']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'description')
        }),
        (_('Display'), {
            'fields': ('color',)
        }),
        (_('Advanced'), {
            'fields': ('extra_data', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def article_count(self, obj):
        """Get the number of articles with the tag."""
        return obj.article_count
    article_count.short_description = _('Articles')


class CommentAdmin(admin.ModelAdmin):
    """Admin interface for Comment model."""
    
    list_display = [
        'author_name', 'article_link', 'created_at',
        'is_approved', 'user'
    ]
    list_filter = ['is_approved', 'created_at']
    search_fields = ['author_name', 'author_email', 'content', 'article__title']
    readonly_fields = ['created_at', 'updated_at', 'ip_address', 'user_agent']
    fieldsets = (
        (None, {
            'fields': ('article', 'parent', 'content')
        }),
        (_('Author'), {
            'fields': ('author_name', 'author_email', 'author_website', 'user')
        }),
        (_('Moderation'), {
            'fields': ('is_approved',)
        }),
        (_('Technical'), {
            'fields': ('ip_address', 'user_agent', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
        (_('Advanced'), {
            'fields': ('extra_data',),
            'classes': ('collapse',)
        }),
    )
    
    def article_link(self, obj):
        """Get a link to the article."""
        url = reverse('admin:flex_blog_article_change', args=[obj.article.pk])
        return format_html('<a href="{}">{}</a>', url, obj.article.title)
    article_link.short_description = _('Article')
    
    actions = ['approve_comments', 'reject_comments']
    
    def approve_comments(self, request, queryset):
        """Approve selected comments."""
        queryset.update(is_approved=True)
    approve_comments.short_description = _('Approve selected comments')
    
    def reject_comments(self, request, queryset):
        """Reject selected comments."""
        queryset.delete()
    reject_comments.short_description = _('Reject and delete selected comments')


class MediaAdmin(admin.ModelAdmin):
    """Admin interface for Media model."""
    
    list_display = ['title', 'type', 'size_display', 'created_at']
    list_filter = ['type', 'created_at']
    search_fields = ['title', 'description', 'alt_text']
    readonly_fields = ['type', 'size', 'image_preview', 'created_at', 'updated_at']
    fieldsets = (
        (None, {
            'fields': ('title', 'file', 'description', 'alt_text')
        }),
        (_('Preview'), {
            'fields': ('image_preview',),
        }),
        (_('Technical'), {
            'fields': ('type', 'size', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
        (_('Advanced'), {
            'fields': ('extra_data',),
            'classes': ('collapse',)
        }),
    )
    
    def size_display(self, obj):
        """Display the file size in a human-readable format."""
        if obj.size < 1024:
            return f"{obj.size} B"
        elif obj.size < 1024 * 1024:
            return f"{obj.size / 1024:.1f} KB"
        elif obj.size < 1024 * 1024 * 1024:
            return f"{obj.size / 1024 / 1024:.1f} MB"
        else:
            return f"{obj.size / 1024 / 1024 / 1024:.1f} GB"
    size_display.short_description = _('Size')
    
    def image_preview(self, obj):
        """Display a preview of the image."""
        if obj.is_image:
            return format_html('<img src="{}" alt="{}" style="max-width: 300px; max-height: 300px;" />', 
                             obj.url, obj.title)
        return _("No preview available")
    image_preview.short_description = _('Preview')

# Register the models with the admin site
def register_models(admin_site=admin.site):
    """Register all models with the admin site."""
    # Get models from registry
    Article = model_registry.get_model('article')
    Author = model_registry.get_model('author')
    Category = model_registry.get_model('category')
    Tag = model_registry.get_model('tag')
    Comment = model_registry.get_model('comment')
    Media = model_registry.get_model('media')
    
    # Register models with admin classes
    admin_site.register(Article, ArticleAdmin)
    admin_site.register(Author, AuthorAdmin)
    admin_site.register(Category, CategoryAdmin)
    admin_site.register(Tag, TagAdmin)
    admin_site.register(Comment, CommentAdmin)
    admin_site.register(Media, MediaAdmin)

# Auto-register the models
register_models()
