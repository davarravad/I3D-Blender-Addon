import bpy
from bpy.types import (Panel)
from bpy.props import (
    StringProperty,
    PointerProperty,
    EnumProperty,
    FloatVectorProperty,
    FloatProperty,
    CollectionProperty
)

from .. import xml_i3d
from pathlib import Path

classes = []

# A module value to represent what the field shows when a shader is not selected
shader_default = 'None'
shader_custom = 'Custom'
custom_shader_default = ''
shader_no_variation = 'None'
shader_parameter_max_decimals = 3  # 0-6 per blender properties documentation
SHADER_CACHE = None
STATIC_ITEMS = [
    (shader_default, 'Select a shader', "Select a shader"),
    (shader_custom, 'Load Custom Shader', "Load a custom shader")
]


def register(cls):
    classes.append(cls)
    return cls


@register
class I3DShaderParameter(bpy.types.PropertyGroup):
    name: StringProperty(default='Unnamed Attribute')
    type: EnumProperty(items=[('float', '', ''), ('float2', '', ''), ('float3', '', ''), ('float4', '', '')])
    data_float_1: FloatProperty(precision=shader_parameter_max_decimals)
    data_float_2: FloatVectorProperty(size=2, precision=shader_parameter_max_decimals)
    data_float_3: FloatVectorProperty(size=3, precision=shader_parameter_max_decimals)
    data_float_4: FloatVectorProperty(size=4, precision=shader_parameter_max_decimals)


@register
class I3DShaderTexture(bpy.types.PropertyGroup):
    name: StringProperty(default='Unnamed Texture')
    source: StringProperty(name='Texture source',
                           description='Path to the texture',
                           subtype='FILE_PATH',
                           default=''
                           )
    default_source: StringProperty()


@register
class I3DShaderVariation(bpy.types.PropertyGroup):
    name: StringProperty(default='Error')


def clear_shader(context):
    attributes = context.object.active_material.i3d_attributes
    if not attributes.shader == shader_custom:
        attributes.shader = shader_default
    attributes.custom_shader = custom_shader_default
    attributes.variations.clear()
    attributes.shader_parameters.clear()
    attributes.shader_textures.clear()
    if attributes.shader not in [shader_custom, shader_default]:
        attributes.variation = shader_no_variation


@register
class I3DLoadCustomShader(bpy.types.Operator):
    """Can load in and generate a custom class for a shader, so settings can be set for export"""
    bl_idname = 'i3dio.load_custom_shader'
    bl_label = 'Load custom shader'
    bl_description = ''
    bl_options = {'INTERNAL'}

    material_name: bpy.props.StringProperty(
        name="Material Name",
        description="Name of the material to update",
        default=""
    )

    def execute(self, context):
        # If a material name is provided, use that material.
        if self.material_name:
            if self.material_name not in bpy.data.materials:
                self.report({'ERROR'}, f"Material '{self.material_name}' not found.")
                return {'CANCELLED'}
            attributes = bpy.data.materials[self.material_name].i3d_attributes

        # If no material name is provided, use the active material of the active object.
        else:
            if not context.object or not context.object.active_material:
                self.report({'ERROR'}, "No active object with an active material found.")
                return {'CANCELLED'}
            attributes = context.object.active_material.i3d_attributes

        data_path = bpy.context.preferences.addons['i3dio'].preferences.fs_data_path

        if attributes.custom_shader != custom_shader_default:
            path = str(Path(attributes.custom_shader))
        else:
            path = str(Path(data_path) / "shaders" / f"{attributes.shader}.xml")

        file = attributes.shader
        tree = xml_i3d.parse(bpy.path.abspath(path))
        if tree is None:
            print(f"{file} is not correct xml")
            clear_shader(context)
        else:
            root = tree.getroot()
            if root.tag != 'CustomShader':
                print(f"{file} is xml, but not a properly formatted shader file! Aborting")
                clear_shader(context)
            else:
                attributes.variations.clear()
                base_variation = attributes.variations.add()
                base_variation.name = shader_no_variation
                attributes.variation = base_variation.name

                variations = root.find('Variations')

                if variations is not None:
                    for variation in variations:
                        new_variation = attributes.variations.add()
                        new_variation.name = variation.attrib['name']

        return {'FINISHED'}


def parameter_element_as_dict(parameter):
    parameter_list = []

    if parameter.attrib['type'] == 'float':
        type_length = 1
    elif parameter.attrib['type'] == 'float2':
        type_length = 2
    elif parameter.attrib['type'] == 'float3':
        type_length = 3
    elif parameter.attrib['type'] == 'float4':
        type_length = 4
    else:
        print(f"Shader Parameter type is unknown!")

    def parse_default(default):
        default_parsed = []
        if default is not None:
            default_parsed = default.split()
            # For some reason, Giants shaders has to specify their default values in terms of float4... Where the extra
            # parts compared with what the actual type length is, aren't in any way relevant.
            if len(default_parsed) > type_length:
                default_parsed = default_parsed[:type_length-1]

        default_parsed += ['0']*(type_length-len(default_parsed))
        return default_parsed

    if 'arraySize' in parameter.attrib:
        for child in parameter:
            parameter_list.append({'name': f"{parameter.attrib['name']}{child.attrib['index']}",
                                   'type': parameter.attrib['type'],
                                   'default_value': parse_default(child.text)})
    else:
        parameter_list.append({'name': parameter.attrib['name'],
                               'type': parameter.attrib['type'],
                               'default_value': parse_default(parameter.attrib.get('defaultValue'))})

    return parameter_list


def texture_element_as_dict(texture):
    texture_dictionary = {'name': texture.attrib['name'],
                          'default_file': texture.attrib.get('defaultFilename', '')
                          }
    return texture_dictionary


@register
class I3DLoadCustomShaderVariation(bpy.types.Operator):
    """This function can load the parameters for a given shader variation, assumes that the source is valid,
       such that this operation will never fail"""
    bl_idname = 'i3dio.load_custom_shader_variation'
    bl_label = 'Load shader variation'
    bl_description = ''
    bl_options = {'INTERNAL'}

    material_name: bpy.props.StringProperty(
        name="Material Name",
        description="Name of the material to update",
        default=""
    )

    def execute(self, context):
        # If a material name is provided, use that material.
        if self.material_name:
            if self.material_name not in bpy.data.materials:
                self.report({'ERROR'}, f"Material '{self.material_name}' not found.")
                return {'CANCELLED'}
            attributes = bpy.data.materials[self.material_name].i3d_attributes

        # If no material name is provided, use the active material of the active object.
        else:
            if not context.object or not context.object.active_material:
                return {'FINISHED'}
            attributes = context.object.active_material.i3d_attributes

        data_path = bpy.context.preferences.addons['i3dio'].preferences.fs_data_path

        if attributes.custom_shader != custom_shader_default:
            path = str(Path(attributes.custom_shader))
        else:
            path = str(Path(data_path) / "shaders" / f"{attributes.shader}.xml")

        tree = xml_i3d.parse(bpy.path.abspath(path))
        if tree is None:
            print(f"{path} doesn't exist!")
            clear_shader(context)

        else:
            attributes.shader_parameters.clear()
            attributes.shader_textures.clear()
            root = tree.getroot()

            # TODO: This should not be run every time the variation is changed, but instead stored somewhere
            parameters = root.find('Parameters')
            grouped_parameters = {}
            if parameters is not None:
                for parameter in parameters:
                    group_name = parameter.attrib.get('group', 'mandatory')
                    group = grouped_parameters.setdefault(group_name, [])
                    group.extend(parameter_element_as_dict(parameter))

            textures = root.find('Textures')
            grouped_textures = {}
            if textures is not None:
                for texture in textures:
                    if texture.attrib.get('defaultColorProfile') is not None:
                        group_name = texture.attrib.get('group', 'mandatory')
                        group = grouped_textures.setdefault(group_name, [])
                        group.append(texture_element_as_dict(texture))

            if attributes.variation != shader_no_variation:
                variations = root.find('Variations')
                variation = variations.find(f"./Variation[@name='{attributes.variation}']")
                parameter_groups = ['mandatory'] + variation.attrib.get('groups', '').split()
            else:
                parameter_groups = ['mandatory', 'base']

            for group in parameter_groups:
                parameter_group = grouped_parameters.get(group)
                if parameter_group is not None:
                    for parameter in grouped_parameters[group]:
                        param = attributes.shader_parameters.add()
                        param.name = parameter['name']
                        param.type = parameter['type']
                        data = tuple(map(float, parameter['default_value']))
                        if param.type == 'float':
                            param.data_float_1 = data[0]
                        elif param.type == 'float2':
                            param.data_float_2 = data
                        elif param.type == 'float3':
                            param.data_float_3 = data
                        elif param.type == 'float4':
                            param.data_float_4 = data

                texture_group = grouped_textures.get(group)
                if texture_group is not None:
                    for texture in grouped_textures[group]:
                        tex = attributes.shader_textures.add()
                        tex.name = texture['name']
                        tex.source = texture['default_file']
                        tex.default_source = texture['default_file']

        return {'FINISHED'}


@register
class I3DMigrateShader(bpy.types.Operator):
    """This function migrate the old shader source property to the new shader enum"""
    bl_idname = 'i3dio.migrate_shader'
    bl_label = 'Migrate shader on all materials'
    bl_description = 'Migration of the old shader source property to the new shader enum on all materials in scene'
    bl_options = {'REGISTER', 'UNDO'}

    def extract_parameters_data(self, attr) -> list:
        data = []
        for param in attr.shader_parameters:
            param_data = {
                "name": param.name,
                "type": param.type
            }
            if param.type == 'float':
                param_data["data_float_1"] = param.data_float_1
            elif param.type == 'float2':
                param_data["data_float_2"] = list(param.data_float_2)
            elif param.type == 'float3':
                param_data["data_float_3"] = list(param.data_float_3)
            elif param.type == 'float4':
                param_data["data_float_4"] = list(param.data_float_4)

            data.append(param_data)
        return data

    def extract_textures_data(self, attr) -> list:
        return [{"name": texture.name, "source": texture.source, "default_source": texture.default_source}
                for texture in attr.shader_textures]

    def apply_parameters_data(self, attr, old_parameters_data):
        print(old_parameters_data)
        for old_param in old_parameters_data:
            param = attr.shader_parameters.add()
            param.name = old_param['name']
            param.type = old_param['type']

            if old_param['type'] == 'float':
                param.data_float_1 = old_param['data_float_1']
            elif old_param['type'] == 'float2':
                param.data_float_2 = old_param['data_float_2']
            elif old_param['type'] == 'float3':
                param.data_float_3 = old_param['data_float_3']
            elif old_param['type'] == 'float4':
                param.data_float_4 = old_param['data_float_4']

    def apply_textures_data(self, attr, old_textures_data):
        for old_texture_data in old_textures_data:
            new_texture = attr.shader_textures.add()
            new_texture.name = old_texture_data["name"]
            new_texture.source = old_texture_data["source"]
            new_texture.default_source = old_texture_data["default_source"]

    def execute(self, context):
        global SHADER_CACHE
        data_path = context.preferences.addons['i3dio'].preferences.fs_data_path
        if not data_path or not Path(data_path).exists():
            self.report({'ERROR'}, "The data path is invalid or inaccessible.")
            return {'CANCELLED'}

        fs19_support = Path(data_path) / "fs19Support" / "shaders"
        if not fs19_support.exists():
            self.report({'ERROR'}, f"Could not find the fs19Support folder ({fs19_support})")
            return {'CANCELLED'}

        for mat in bpy.data.materials:
            if mat.i3d_attributes.source:
                attr = mat.i3d_attributes

                # Need to collect all old data first, or else it will be lost when it assign the shader,
                # because the operator will clear the variation and parameter data
                old_path = Path(attr.source)

                shader_name = old_path.stem
                old_variation = attr.variation
                old_parameters_data = self.extract_parameters_data(attr)
                old_textures_data = self.extract_textures_data(attr)

                matching_files = list(fs19_support.glob(f"{shader_name}*.xml"))

                allowed_values = [item[0] for item in SHADER_CACHE]
                if shader_name in allowed_values:
                    attr.shader = shader_name
                elif shader_name in [f.stem for f in matching_files]:
                    attr.shader = shader_custom
                    attr.custom_shader = str(fs19_support + f"\\{shader_name}.xml")
                else:
                    if not old_path.exists():
                        self.report({'WARNING'}, f"Could not find the shader file: {old_path}, skipping: {mat.name}")
                        continue
                    attr.shader = shader_custom
                    attr.custom_shader = str(old_path)

                attr.variation = old_variation

                # Clear old shader parameters and textures (or else we will end up with duplicates in the panel)
                mat.i3d_attributes.shader_parameters.clear()
                mat.i3d_attributes.shader_textures.clear()

                # Reapply shader parameters & textures
                self.apply_parameters_data(attr, old_parameters_data)
                self.apply_textures_data(attr, old_textures_data)

        self.report({'INFO'}, "Shader migration complete")
        return {'FINISHED'}


@register
class I3DMaterialShader(bpy.types.PropertyGroup):
    # NOTE Keep this internaly to set old values to the new shader enum
    source: StringProperty(name='Shader Source',
                           description='Path to the shader',
                           subtype='FILE_PATH',
                           )

    def custom_shader_setter(self, value):
        try:
            self['custom_shader']
        except KeyError:
            self['custom_shader'] = value
            if self['custom_shader'] != custom_shader_default:
                bpy.ops.i3dio.load_custom_shader()
        else:
            if self['custom_shader'] != value:
                self['custom_shader'] = value
                if self['custom_shader'] != custom_shader_default:
                    bpy.ops.i3dio.load_custom_shader()

    def custom_shader_getter(self):
        return self.get('custom_shader', custom_shader_default)

    custom_shader: StringProperty(name='Custom Shader',
                                  description='Path to the custom shader',
                                  subtype='FILE_PATH',
                                  default=custom_shader_default,
                                  set=custom_shader_setter,
                                  get=custom_shader_getter
                                  )

    # New code setup
    def shader_items_update(self, context):
        """ Returns a list of all shader files in the FS shader directory """
        global SHADER_CACHE
        if SHADER_CACHE:
            return STATIC_ITEMS + SHADER_CACHE

        data_path = bpy.context.preferences.addons['i3dio'].preferences.fs_data_path

        shader_dir = Path(data_path) / 'shaders' if data_path else ''

        if shader_dir == '' or not shader_dir.exists():
            return [('No shaders found', 'No shaders found', "No shaders found")]

        shader_files = [shader_file.stem for shader_file in shader_dir.glob('*.xml')]
        SHADER_CACHE = [(shader, shader, "Shader") for shader in shader_files]
        return STATIC_ITEMS + SHADER_CACHE

    def shader_setter(self, selected_index):
        # To get the name of the shader instead of index
        selected_shader = self.shader_items_update(bpy.context)[selected_index][0]
        if self.get('shader') != selected_index:
            self['shader'] = selected_index

            # Storing the name of the shader (might be useful)
            self['shader_name'] = selected_shader

            if selected_shader not in [shader_custom, shader_default]:
                # Ensure that materials generated through the API don't modify the scene's
                # active object or its material.
                owner_mat = self.id_data if isinstance(self.id_data, bpy.types.Material) else None
                active_mat = bpy.context.active_object.active_material if bpy.context.active_object else None

                # Only run operator if owner_mat is the active material
                if owner_mat == active_mat:
                    bpy.ops.i3dio.load_custom_shader()
                    bpy.ops.i3dio.load_custom_shader_variation()
            else:
                clear_shader(bpy.context)

    def shader_getter(self):
        default_index = next((index for index, (key, _, _) in
                              enumerate(self.shader_items_update(bpy.context)) if key == shader_default), 0)
        return self.get('shader', default_index)

    shader: EnumProperty(name='Shader',
                         description='The shader',
                         default=None,
                         items=shader_items_update,
                         options=set(),
                         update=None,
                         get=shader_getter,
                         set=shader_setter,
                         )

    def variation_items_update(self, context):
        items = []
        if self.variations:
            for variation in self.variations:
                items.append((f'{variation.name}', f'{variation.name}', f"The shader variation '{variation.name}'"))
        return items

    def variation_setter(self, value):
        if self.get('variation') == value:
            return
        self['variation'] = value

        # Ensure that materials generated through the API don't modify the scene's active object or its material.
        owner_mat = self.id_data if isinstance(self.id_data, bpy.types.Material) else None
        active_mat = bpy.context.active_object.active_material if bpy.context.active_object else None

        # Only run operator if owner_mat is the active material
        if owner_mat == active_mat:
            bpy.ops.i3dio.load_custom_shader_variation()

    def variation_getter(self):
        return self.get('variation', shader_no_variation)

    variation: EnumProperty(name='Variation',
                            description='The shader variation',
                            default=None,
                            items=variation_items_update,
                            options=set(),
                            update=None,
                            get=variation_getter,
                            set=variation_setter
                            )

    variations: CollectionProperty(type=I3DShaderVariation)
    shader_parameters: CollectionProperty(type=I3DShaderParameter)
    shader_textures: CollectionProperty(type=I3DShaderTexture)


@register
class I3D_IO_PT_shader(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_label = "I3D Shader Settings"
    bl_context = 'material'

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.active_material is not None

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        material = bpy.context.active_object.active_material

        layout.operator("i3dio.migrate_shader")

        layout.prop(material.i3d_attributes, 'shader')
        if material.i3d_attributes.shader == shader_custom:
            layout.prop(material.i3d_attributes, 'custom_shader')
        if material.i3d_attributes.variations:
            layout.prop(material.i3d_attributes, 'variation')


@register
class I3D_IO_PT_shader_parameters(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_label = "Parameters"
    bl_context = 'material'
    bl_parent_id = 'I3D_IO_PT_shader'

    @classmethod
    def poll(cls, context):
        try:
            is_active = bool(context.object.active_material.i3d_attributes.shader_parameters)
        except AttributeError:
            is_active = False
        return is_active

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = False
        layout.use_property_decorate = False
        column = layout.column(align=True)
        parameters = bpy.context.active_object.active_material.i3d_attributes.shader_parameters
        for parameter in parameters:
            if parameter.type == 'float':
                property_type = 'data_float_1'
            elif parameter.type == 'float2':
                property_type = 'data_float_2'
            elif parameter.type == 'float3':
                property_type = 'data_float_3'
            else:
                property_type = 'data_float_4'

            column.row(align=True).prop(parameter, property_type, text=parameter.name)


@register
class I3D_IO_PT_shader_textures(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_label = "Textures"
    bl_context = 'material'
    bl_parent_id = 'I3D_IO_PT_shader'

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = False
        layout.use_property_decorate = False
        column = layout.column(align=True)
        textures = bpy.context.active_object.active_material.i3d_attributes.shader_textures
        for texture in textures:
            column.row(align=True).prop(texture, 'source', text=texture.name)

    @classmethod
    def poll(cls, context):
        try:
            is_active = bool(context.object.active_material.i3d_attributes.shader_textures)
        except AttributeError:
            is_active = False
        return is_active


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Material.i3d_attributes = PointerProperty(type=I3DMaterialShader)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Material.i3d_attributes
