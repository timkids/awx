import json
import warnings
import re

from coreapi.document import Object, Link

from django.conf import settings
from django.utils.encoding import smart_str
from rest_framework import exceptions, serializers
from rest_framework.permissions import AllowAny
from rest_framework.renderers import CoreJSONRenderer
from rest_framework.response import Response
from rest_framework.schemas.openapi import SchemaGenerator
from rest_framework.schemas.openapi import AutoSchema as DRFAuthSchema
from rest_framework.schemas.utils import is_list_view
from rest_framework.views import APIView
from rest_framework.fields import empty

from rest_framework_swagger import renderers


class SuperUserSchemaGenerator(SchemaGenerator):
    def get_schema(self, *args, **kwargs):
        schema = super().get_schema(*args, **kwargs)
        schema["info"]["title"] = "Ansible Automation Platform controller API"
        schema["info"][
            "description"
        ] = "The Ansible Tower API Reference Manual provides in-depth documentation for Tower's REST API, including examples on how to integrate with it."
        # schema["info"]["termsOfService"] = "https://example.com/tos.html"
        schema["components"]['securitySchemes'] = {}
        schema["components"]['securitySchemes']['csrfAuth'] = {'type': 'apiKey', 'in': 'cookie', 'name': 'awx_sessionid'}

        revised_paths = {}
        # Replace {version} with current version
        for path, node in schema['paths'].items():
            # change {version} in paths to the actual default API version (e.g., v2)
            revised_paths[path.replace('{version}', settings.REST_FRAMEWORK['DEFAULT_VERSION'])] = node
            for method in node:
                # remove the required `version` parameter
                for param in node[method].get('parameters'):
                    if param['in'] == 'path' and param['name'] == 'version':
                        node[method]['parameters'].remove(param)

        schema["paths"] = revised_paths

        return schema

    def has_view_permissions(self, path, method, view):
        #
        # Generate the Swagger schema as if you were a superuser and
        # permissions didn't matter; this short-circuits the schema path
        # discovery to include _all_ potential paths in the API.
        #
        return True


class AutoSchema(DRFAuthSchema):
    def get_operation(self, path, method):
        operation = super(AutoSchema, self).get_operation(path, method)

        # Deprecated properties for the operation
        operation['deprecated'] = getattr(self.view, 'deprecated', False)

        permission_classes = getattr(self.view, 'permission_classes', [])

        # Security properties for the operation
        authenticated_operation = len(permission_classes) > 0
        for permission_class in permission_classes:
            if permission_class == AllowAny:
                authenticated_operation = False

        if authenticated_operation:
            operation['security'] = [{'csrfAuth': []}]

        # Summary for the operation
        method_name = getattr(self.view, 'action', method.lower())
        if is_list_view(path, method, self.view):
            action = 'List'
        elif method_name not in self.method_mapping:
            action = self._to_camel_case(method_name)
        else:
            action = self.method_mapping[method.lower()]

        # Format drf action for good summary
        # Example: partialUpdate must be 'Partial update' on documentation
        action = result = action[0].upper() + action[1:]
        res_list = []
        res_list = re.findall('[A-Z][^A-Z]*', action)
        action = (' '.join(res_list)).capitalize()

        summary = ""
        if hasattr(self.view, 'model'):
            model = str(self.view.model._meta.verbose_name_plural).title()
            if hasattr(self.view, 'parent_model'):
                parent_model = str(self.view.parent_model._meta.verbose_name_plural).title()
                summary = "{} {} for {}".format(smart_str(action), smart_str(model), smart_str(parent_model))
            else:
                summary = "{} {}".format(smart_str(action), smart_str(model))
        else:
            description_lines = self.get_description(path, method).splitlines()
            if len(description_lines) > 0:
                summary = smart_str(description_lines[0])
            else:
                warnings.warn('Could not determine an openapi summary for View {}'.format(self.view.__class__.__name__))

        operation['summary'] = summary
        # print("Summary {}".format(operation['summary']))

        return operation

    def get_tags(self, path, method):
        tags = []

        if hasattr(self.view, 'openapi_tag'):
            tags = [(str(self.view.openapi_tag).title())]
            # print("Swagger topic for {} -> {}".format(str(self.view.__class__.__name__), tags))
        elif hasattr(self.view, 'parent_model'):
            # print("Parent Model for {} -> {}".format(str(self.view.__class__.__name__), tags))
            tags = [str(self.view.parent_model._meta.verbose_name_plural).title()]
        elif hasattr(self.view, 'model'):
            # print("Model for {} -> {}".format(str(self.view.__class__.__name__), tags))
            tags = [str(self.view.model._meta.verbose_name_plural).title()]
        else:
            warnings.warn('Could not determine a Swagger tag for View {}'.format(self.view.__class__.__name__))
        return tags

    def get_description(self, path, method):
        setattr(self.view, 'openapi_method', method)
        description = super(AutoSchema, self).get_description(path, method)
        return description

    def map_serializer(self, serializer):
        # Assuming we have a valid serializer instance.
        required = []
        properties = {}

        for field in serializer.fields.values():
            field_info = {}
            if hasattr(self.view, 'model'):
                serializer_info = self.view.metadata_class().get_serializer_info(serializer)
                field_info = serializer_info[field.field_name]

            if isinstance(field, serializers.HiddenField):
                continue

            if field.required:
                required.append(field.field_name)

            schema = self.map_field(field)
            if field.read_only:
                schema['readOnly'] = True
            if field.write_only:
                schema['writeOnly'] = True
            if field.allow_null:
                schema['nullable'] = True
            if field.default is not None and field.default != empty and not callable(field.default):
                schema['default'] = field.default
            if field.help_text:
                schema['description'] = str(field.help_text)
            elif 'help_text' in field_info:
                schema['description'] = str(field_info['help_text'])
            self.map_field_validators(field, schema)

            properties[field.field_name] = schema

        result = {'type': 'object', 'properties': properties}
        if required:
            result['required'] = required

        return result

    def get_operation_id_base(self, path, method, action):
        super_operation_id_base = super(AutoSchema, self).get_operation_id_base(path, method, action)

        operation_id_base = super_operation_id_base
        if hasattr(self.view, 'get_operation_base_id'):
            print("Operation_Id_Base {}".format(self.view.get_operation_base_id()))

        if hasattr(self.view, 'operation_id_base'):
            operation_id_base = self.view.operation_id_base
        elif hasattr(self.view, 'parent_model'):
            operation_id_base = str(self.view.parent_model._meta.verbose_name_plural).title() + super_operation_id_base

        if hasattr(self.view, 'copy_return_serializer_class'):
            operation_id_base = str(self.view.__class__.__name__)

        return operation_id_base


class SwaggerSchemaView(APIView):
    _ignore_model_permissions = True
    exclude_from_schema = True
    permission_classes = [AllowAny]
    renderer_classes = [CoreJSONRenderer, renderers.OpenAPIRenderer, renderers.SwaggerUIRenderer]

    def get(self, request):
        # generator = SuperUserSchemaGenerator(title='Ansible Automation Platform controller API', patterns=None, urlconf=None)
        generator = SuperUserSchemaGenerator(title='Ansible Automation Platform controller API')
        schema = generator.get_schema(request=request)
        # python core-api doesn't support the deprecation yet, so track it
        # ourselves and return it in a response header
        _deprecated = []

        # By default, DRF OpenAPI serialization places all endpoints in
        # a single node based on their root path (/api).  Instead, we want to
        # group them by topic/tag so that they're categorized in the rendered
        # output
        document = schema._data.pop('api')
        for path, node in document.items():
            if isinstance(node, Object):
                for action in node.values():
                    topic = getattr(action, 'topic', None)
                    if topic:
                        schema._data.setdefault(topic, Object())
                        schema._data[topic]._data[path] = node

                    if isinstance(action, Object):
                        for link in action.links.values():
                            if link.deprecated:
                                _deprecated.append(link.url)
            elif isinstance(node, Link):
                topic = getattr(node, 'topic', None)
                if topic:
                    schema._data.setdefault(topic, Object())
                    schema._data[topic]._data[path] = node

        if not schema:
            raise exceptions.ValidationError('The schema generator did not return a schema Document')

        return Response(schema, headers={'X-Deprecated-Paths': json.dumps(_deprecated)})
