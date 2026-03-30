import logging
import os

from io_storages.langfuse.models import LangfuseImportStorage
from io_storages.serializers import ImportStorageSerializer
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)


class LangfuseStorageSerializerMixin:
    secure_fields = ['langfuse_secret_key']

    def to_representation(self, instance):
        result = super().to_representation(instance)
        for attr in self.secure_fields:
            result.pop(attr, None)
        return result

    def validate(self, data):
        data = super().validate(data)
        if not data.get('langfuse_host'):
            return data

        storage = self.instance
        if storage:
            for key, value in data.items():
                setattr(storage, key, value)
        else:
            if 'id' in self.initial_data:
                storage_object = self.Meta.model.objects.get(id=self.initial_data['id'])
                for attr in self.secure_fields:
                    data[attr] = data.get(attr) or getattr(storage_object, attr)
            storage = self.Meta.model(**data)

        try:
            storage.validate_connection()
        except Exception as e:
            logger.info(f'Langfuse connection validation failed: {e}', exc_info=True)
            raise ValidationError(
                f'Cannot connect to Langfuse at {storage.langfuse_host}. '
                f'Please check your host URL and API keys.'
            )
        return data


class LangfuseImportStorageSerializer(LangfuseStorageSerializerMixin, ImportStorageSerializer):
    type = serializers.ReadOnlyField(default=os.path.basename(os.path.dirname(__file__)))

    class Meta:
        model = LangfuseImportStorage
        fields = '__all__'
