from django.db import models
import uuid
from django.conf import settings
from django.utils import timezone
from .constant import *

class SoftDeletedQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_deleted=False)
    
    def deleted(self):
        return self.filter(is_deleted=True)

class SoftDeletedManager(models.Manager):
    def get_queryset(self):
        return SoftDeletedQuerySet(self.model, using=self._db).active()  
    
    def all_with_deleted(self):
        return SoftDeletedQuerySet(self.model, using=self._db).all()

    def deleted(self):
        return SoftDeletedQuerySet(self.model, using=self._db).deleted()  

class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_%(class)s')

    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='updated_%(class)s')
    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='deleted_%(class)s')
    
    objects = models.Manager() 
    active_objects = SoftDeletedManager()

    class Meta:
        abstract = True
        
    def soft_delete(self, deleted_by=None):
        self.is_deleted = True
        self.deleted_by = deleted_by
        self.save()

    def __str__(self):
        return f"{self.__class__.__name__} ({self.id})"