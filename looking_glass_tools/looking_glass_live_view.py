# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import bpy
import gpu
import json
import subprocess
import logging
from bgl import *
from math import *
from mathutils import *
from bpy.types import AddonPreferences, PropertyGroup
from bpy.props import FloatProperty, PointerProperty

# The shaders are stored as strings
# The vertex shader yields the texture coordinates for the fragment shader
shaderVertString = """
varying vec2 v_texCoord0;
void main()
{
	gl_Position =  ftransform();
	v_texCoord0 = vec2(gl_MultiTexCoord0);    
}
"""

shaderFragString = """
uniform vec4 black;
varying vec2 v_texCoord0;
uniform sampler2D tex0;
uniform sampler2D tex1;
uniform sampler2D tex2;
uniform sampler2D tex3;
uniform sampler2D tex4;
uniform sampler2D tex5;
uniform sampler2D tex6;
uniform sampler2D tex7;
uniform sampler2D tex8;
uniform sampler2D tex9;
uniform sampler2D tex10;
uniform sampler2D tex11;
uniform sampler2D tex12;
uniform sampler2D tex13;
uniform sampler2D tex14;
uniform sampler2D tex15;
uniform sampler2D tex16;
uniform sampler2D tex17;
uniform sampler2D tex18;
uniform sampler2D tex19;
uniform sampler2D tex20;
uniform sampler2D tex21;
uniform sampler2D tex22;
uniform sampler2D tex23;
uniform sampler2D tex24;
uniform sampler2D tex25;
uniform sampler2D tex26;
uniform sampler2D tex27;
uniform sampler2D tex28;
uniform sampler2D tex29;
uniform sampler2D tex30;
uniform sampler2D tex31;

//parameters
uniform float pitch;
uniform float tilt;
uniform float center;
uniform float invView; 
uniform float flipX; 
uniform float flipY; 
uniform float subp; 
uniform int ri; //red Index
uniform int bi; //blue Index
uniform float tilesX; 
uniform float tilesY;
uniform float windowW;
uniform float windowH;
uniform float windowX;
uniform float windowY;
uniform float screenW;
uniform float screenH;

void main()
{
	black = vec4(0.0, 0.0, 0.0, 1.0);
	vec4 rgb[3]; //array of three vec4s
	vec3 nuv = vec3(v_texCoord0.xy, 0.0);
	vec2 iUv = v_texCoord0.xy;
	
	sampler2D texArray[] = {
		tex0, tex1, tex2, tex3, tex4, tex5, tex6, tex7, tex8, tex9, tex10, tex11, tex12, tex13, tex14, tex15, tex16, tex17, tex18, tex19, tex20, tex21, tex22, tex23, tex24, tex25, tex26, tex27, tex28, tex29, tex30, tex31
	};
	
	gl_FragColor = black;
	
	//Flip UVs if necessary
	nuv.x = (1.0 - flipX) * nuv.x + flipX * (1.0 - nuv.x);
	nuv.y = (1.0 - flipY) * nuv.y + flipY * (1.0 - nuv.y);
	
	
	for (int i = 0; i < 3; i++) {
		nuv.z = (nuv.x + float(i) * subp + iUv.y * tilt) * pitch - center;
		nuv.z = mod(nuv.z + ceil(abs(nuv.z)), 1.0);
		nuv.z = (1.0 - invView) * nuv.z + invView * (1.0 - nuv.z);
		float z = floor(nuv.z * tilesX * tilesY);

		// we do not need to sample a quilt, can access the textures
		// directly via array
		rgb[i] = texture2D(texArray[z], nuv.xy);
	}

	//gl_FragColor = texture2D(canvas_tex, v_texCoord0);
	gl_FragColor = vec4(rgb[0].r, rgb[1].g, rgb[2].b, 1);
}
"""

# global variable for the shader
program = None

def create_shader_program():
	''' create and attach a shader program made from vertex and fragment shader '''
	global program
	program = glCreateProgram()

	shaderVert = glCreateShader(GL_VERTEX_SHADER)
	shaderFrag = glCreateShader(GL_FRAGMENT_SHADER)

	glShaderSource(shaderVert, shaderVertString)
	glShaderSource(shaderFrag, shaderFragString)

	glCompileShader(shaderVert)
	glCompileShader(shaderFrag)

	glAttachShader(program, shaderVert)
	glAttachShader(program, shaderFrag)

	glLinkProgram(program)
	
	#Buffer is used in BGL instead of pointers
	success = Buffer(GL_INT, [1])
	glGetProgramiv(program, GL_LINK_STATUS, success)
	if (success[0] == GL_TRUE):
		print("Shader linking successfull!")

	glDeleteShader(shaderVert)
	glDeleteShader(shaderFrag)

class OffScreenDraw(bpy.types.Operator):
	bl_idname = "view3d.offscreen_draw"
	bl_label = "Looking Glass Live View"

	_handle_calc = None
	_handle_draw = None
	_handle_draw_3dview = None
	is_enabled = False
	
	# store the area from where the operator is invoked
	area = None

	#dummy vars for one-time computations
	newPitch = 0.0
	newTilt = 0.0
	subPixelSize = 0.0
	redIndex = 0
	blueIndex = 0
	
	@staticmethod
	def compute_view_angles(view_cone, total_views):
		view_angles = list()
		
		for i in range(total_views):
			tmp_view = (((-1)*view_cone) / 2 + view_cone * (i / (total_views-1))) * (-1) #the last (-1) is to invert the order
			view_angles.append(tmp_view)
			
		return view_angles
	
	@staticmethod
	def compute_x_offsets(convergence_distance, view_angles):
		x_offsets = list()
		
		for ang in view_angles:
			tmp_offset = convergence_distance * tan(ang * 0.5)
			x_offsets.append(tmp_offset)
			
		return x_offsets
	
	@staticmethod
	def compute_projection_offsets(x_offsets, aspect_ratio, size):
		projection_offsets = list()
		
		for off in x_offsets:
			tmp_proj = off / (aspect_ratio * size)
			projection_offsets.append(tmp_proj)
			
		return projection_offsets
	
	@staticmethod
	def setup_modelview_matrices(modelview_matrix, x_offsets):
		''' shift the camera position on the local x-axis by x_offset '''
		modelview_matrices = list()
		
		for off in x_offsets:
			#matrices in Blender need to be copied, otherwise it is only a link
			mv_temp = modelview_matrix.copy()
			mv_temp[0][3] += off
			modelview_matrices.append(mv_temp)
			
		return modelview_matrices
	
	@staticmethod
	def setup_projection_matrices(projection_matrix, projection_offsets):
		''' the projection matrices need to be offset (similar to lens shift in Cycles) '''
		projection_matrices = list()
		
		for off in projection_offsets:
			#matrices in Blender need to be copied, otherwise it is only a link
			proj_temp = projection_matrix.copy()
			proj_temp[0][2] += off
			projection_matrices.append(proj_temp)
			
		return projection_matrices
	
	@staticmethod
	def update_offscreens(self, context, offscreens, modelview_matrices, projection_matrices):
		''' helper method to update a whole list of offscreens '''
		
		# find the image editor window and create a faux context
		for window in bpy.context.window_manager.windows:
			screen = window.screen
			for area in screen.areas:
				if area.type == 'VIEW_3D':
					for region in area.regions:
						if region.type == 'WINDOW':
							for space in area.spaces:
								if space.type == 'VIEW_3D': 
									override = {'area': area,
									'region': region,
									'space_data': space,
									'scene': context.scene,
									}
			
		for i in range(len(offscreens)):
			self._update_offscreen_m(override, offscreens[i], modelview_matrices[i], projection_matrices[i])
			
	@staticmethod
	def draw_callback_px(self, context):
		''' Manges the draw handler '''
		scene = context.scene
		render = scene.render
		wm = context.window_manager
		
		#should be the same aspect ratio as the looking glass display
		aspect_ratio = scene.render.resolution_x / scene.render.resolution_y
		
		total_views = wm.tilesHorizontal * wm.tilesVertical
		
		camera_active = scene.camera
		modelview_matrix, projection_matrix = self._setup_matrices_from_camera(context, camera_active)
		
		# compute the field of view from projection matrix directly
		# because focal length fov in Cycles is a disc
		view_cone = 2.0*atan( 1.0/projection_matrix[1][1] ) 	   
		view_angles = self.compute_view_angles(view_cone, total_views)
		
		if camera_active.data.dof_object == None:
			convergence_distance = camera_active.data.dof_distance
		else:
			convergence_vector = camera_active.location - camera_active.data.dof_object.location
			convergence_distance = convergence_vector.magnitude

		size = convergence_distance * tan(view_cone * 0.5)
		
		x_offsets = self.compute_x_offsets(convergence_distance, view_angles)		
		projection_offsets = self.compute_projection_offsets(x_offsets, aspect_ratio, size)
		
		# prepare offscreen render buffers
		offscreens = self._setup_offscreens(context, total_views)

		#create lists of matrices for modelview and projection
		modelview_matrices = self.setup_modelview_matrices(modelview_matrix, x_offsets)
		projection_matrices = self.setup_projection_matrices(projection_matrix, projection_offsets)
		
		# render the scene total_views times from different angles and store the results in offscreen objects
		self.update_offscreens(self, context, offscreens, modelview_matrices, projection_matrices)		
		

		self._opengl_draw(context, offscreens, aspect_ratio, 1.0)
		
	@staticmethod
	def draw_callback_3dview(self, context):
		''' Redraw the are stored in self.area whenever the 3D view updates '''
		self.area.tag_redraw()

	@staticmethod
	def handle_add(self, context):
		''' The handler in the image editor is to actually draw the lenticular image.
			The handler in the 3D view is meant to send update triggers to the image
			editor handler whenever the 3D view updates. '''
		OffScreenDraw._handle_draw = bpy.types.SpaceImageEditor.draw_handler_add(
				self.draw_callback_px, (self, context),
				'WINDOW', 'POST_PIXEL',
				)
		OffScreenDraw._handle_draw_3dview = bpy.types.SpaceView3D.draw_handler_add(
				self.draw_callback_3dview, (self, context),
				'WINDOW', 'POST_PIXEL',
				)

	@staticmethod
	def handle_remove():
		if OffScreenDraw._handle_draw is not None:
			bpy.types.SpaceImageEditor.draw_handler_remove(OffScreenDraw._handle_draw, 'WINDOW')

		OffScreenDraw._handle_draw = None
		
		if OffScreenDraw._handle_draw_3dview is not None:
			bpy.types.SpaceView3D.draw_handler_remove(OffScreenDraw._handle_draw_3dview, 'WINDOW')

		OffScreenDraw._handle_draw_3dview = None

	@staticmethod
	def _setup_offscreens(context, num_offscreens = 1):
		''' create off-screen buffers '''
		offscreens = list()
		for i in range(num_offscreens):
			try:
				offscreen = gpu.offscreen.new(512, 256)
			except Exception as e:
				print(e)
				offscreen = None
			offscreens.append(offscreen)
		
		# do not return a list when only one offscreen is set up	
		if num_offscreens == 1:
			return offscreens[0]
		else:
			return offscreens
	
	@staticmethod
	def _setup_matrices_from_camera(context, camera):
		scene = context.scene
		render = scene.render
		
		modelview_matrix = camera.matrix_world.inverted()
		projection_matrix = camera.calc_matrix_camera(
				render.resolution_x,
				render.resolution_y,
				render.pixel_aspect_x,
				render.pixel_aspect_y,
				)
				
		return modelview_matrix, projection_matrix
		
	@staticmethod
	def _update_offscreen_m(context, offscreen, modelview_matrix, projection_matrix):
		''' render viewport into offscreen buffer using matrices '''
		scene = bpy.context.scene

		offscreen.draw_view3d(
				scene,
				context['space_data'],
				context['region'],
				projection_matrix,
				modelview_matrix,
				)

	@staticmethod   		 
	def create_image(width, height, target=GL_RGBA):
		"""create an empty image, dimensions pow2"""
		if target == GL_RGBA:
			target, internal_format, dimension  = GL_RGBA, GL_RGB, 3
		else:
			target, internal_format, dimension = GL_DEPTH_COMPONENT32, GL_DEPTH_COMPONENT, 1

		null_buffer = Buffer(GL_BYTE, [(width + 1) * (height + 1) * dimension])

		id_buf = Buffer(GL_INT, 1)
		glGenTextures(1, id_buf)

		tex_id = id_buf.to_list()[0]
		glBindTexture(GL_TEXTURE_2D, tex_id)

		glTexImage2D(GL_TEXTURE_2D, 0, target, width, height, 0, internal_format, GL_UNSIGNED_BYTE, null_buffer)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

		if target == GL_DEPTH_COMPONENT32:
			glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_COMPARE_MODE, GL_NONE)

		glCopyTexImage2D(GL_TEXTURE_2D, 0, target, 0, 0, width, height, 0)

		glBindTexture(GL_TEXTURE_2D, 0)

		del null_buffer
		
		return tex_id
	
	@staticmethod
	def update_image(tex_id, target=GL_RGBA, texture=GL_TEXTURE0):
		"""copy the current buffer to the image"""
		glActiveTexture(texture)
		glBindTexture(GL_TEXTURE_2D, tex_id)
		glCopyTexSubImage2D(GL_TEXTURE_2D, 0, 100, 10, 0, 0, 256, 128)
		glBindTexture(GL_TEXTURE_2D, 0)
	
	@staticmethod
	def delete_image(tex_id):
		"""clear created image"""
		id_buf = Buffer(GL_INT, 1)
		id_buf.to_list()[0] = tex_id

		if glIsTexture(tex_id):
			glDeleteTextures(1, id_buf)

	def _opengl_draw(self, context, offscreens, aspect_ratio, scale):
		''' OpenGL code to draw a rectangle in a window '''

		scn = context.scene
		wm = context.window_manager

		glDisable(GL_DEPTH_TEST)	   

		# view setup
		glMatrixMode(GL_PROJECTION)
		glPushMatrix()
		glLoadIdentity()

		glOrtho(-1, 1, -1, 1, -15, 15)

		act_tex = Buffer(GL_INT, 1)
		glGetIntegerv(GL_TEXTURE_2D, act_tex)

		viewport = Buffer(GL_INT, 4)
		glGetIntegerv(GL_VIEWPORT, viewport)

		width = floor(wm.screenW)
		height = floor(wm.screenH)
		
		glViewport(viewport[0], viewport[1], width, height)
		glScissor(viewport[0], viewport[1], width, height)
		
		# the shaders are already compiled, ready to be used
		glUseProgram(program)
		
		#sent all the parameters to the shader
		pitchUniformLocation = glGetUniformLocation(program, "pitch")
		glUniform1f(pitchUniformLocation, self.newPitch)
		tiltUniformLocation = glGetUniformLocation(program, "tilt")
		glUniform1f(tiltUniformLocation, self.newTilt)
		centerUniformLocation = glGetUniformLocation(program, "center")
		glUniform1f(centerUniformLocation, wm.center)
		invViewUniformLocation = glGetUniformLocation(program, "invView")
		glUniform1f(invViewUniformLocation, wm.invView)
		flipXUniformLocation = glGetUniformLocation(program, "flipX")
		glUniform1f(flipXUniformLocation, wm.flipImageX)
		flipYUniformLocation = glGetUniformLocation(program, "flipY")
		glUniform1f(flipXUniformLocation, wm.flipImageY)
		subpUniformLocation = glGetUniformLocation(program, "subp")
		glUniform1f(subpUniformLocation, self.subPixelSize)
		riUniformLocation = glGetUniformLocation(program, "ri")
		glUniform1f(riUniformLocation, self.redIndex)
		biUniformLocation = glGetUniformLocation(program, "bi")
		glUniform1f(biUniformLocation, self.blueIndex)
		tilesXUniformLocation = glGetUniformLocation(program, "tilesX")
		glUniform1f(tilesXUniformLocation, wm.tilesHorizontal)
		tilesYUniformLocation = glGetUniformLocation(program, "tilesY")
		glUniform1f(tilesYUniformLocation, wm.tilesVertical)
		screenWUniformLocation = glGetUniformLocation(program, "screenW")
		glUniform1f(screenWUniformLocation, wm.screenW)
		screenHUniformLocation = glGetUniformLocation(program, "screenH")
		glUniform1f(screenHUniformLocation, wm.screenH)

		# setting up all 32 textures by hand is ridiculous
		# there must be a better way!
		texloc = 0
		texLoc = glGetUniformLocation(program, "tex0")
		glUniform1i(texLoc, 0)  	  
		texLoc = glGetUniformLocation(program, "tex1")
		glUniform1i(texLoc, 1)  	  
		texLoc = glGetUniformLocation(program, "tex2")
		glUniform1i(texLoc, 2)  	  
		texLoc = glGetUniformLocation(program, "tex3")
		glUniform1i(texLoc, 3)  	  
		texLoc = glGetUniformLocation(program, "tex4")
		glUniform1i(texLoc, 4)  	  
		texLoc = glGetUniformLocation(program, "tex5")
		glUniform1i(texLoc, 5)  	  
		texLoc = glGetUniformLocation(program, "tex6")
		glUniform1i(texLoc, 6)  	  
		texLoc = glGetUniformLocation(program, "tex7")
		glUniform1i(texLoc, 7)  	  
		texLoc = glGetUniformLocation(program, "tex8")
		glUniform1i(texLoc, 8)  	  
		texLoc = glGetUniformLocation(program, "tex9")
		glUniform1i(texLoc, 9)  	  
		texLoc = glGetUniformLocation(program, "tex10")
		glUniform1i(texLoc, 10) 	   
		texLoc = glGetUniformLocation(program, "tex11")
		glUniform1i(texLoc, 11)
		texLoc = glGetUniformLocation(program, "tex12")
		glUniform1i(texLoc, 12)
		texLoc = glGetUniformLocation(program, "tex13")
		glUniform1i(texLoc, 13)
		texLoc = glGetUniformLocation(program, "tex14")
		glUniform1i(texLoc, 14)
		texLoc = glGetUniformLocation(program, "tex15")
		glUniform1i(texLoc, 15)
		texLoc = glGetUniformLocation(program, "tex16")
		glUniform1i(texLoc, 16) 	   
		texLoc = glGetUniformLocation(program, "tex17")
		glUniform1i(texLoc, 17) 	   
		texLoc = glGetUniformLocation(program, "tex18")
		glUniform1i(texLoc, 18) 	   
		texLoc = glGetUniformLocation(program, "tex19")
		glUniform1i(texLoc, 19) 	   
		texLoc = glGetUniformLocation(program, "tex20")
		glUniform1i(texLoc, 20) 	   
		texLoc = glGetUniformLocation(program, "tex21")
		glUniform1i(texLoc, 21) 	   
		texLoc = glGetUniformLocation(program, "tex22")
		glUniform1i(texLoc, 22) 	   
		texLoc = glGetUniformLocation(program, "tex23")
		glUniform1i(texLoc, 23) 	   
		texLoc = glGetUniformLocation(program, "tex24")
		glUniform1i(texLoc, 24) 	   
		texLoc = glGetUniformLocation(program, "tex25")
		glUniform1i(texLoc, 25) 	   
		texLoc = glGetUniformLocation(program, "tex26")
		glUniform1i(texLoc, 26) 	   
		texLoc = glGetUniformLocation(program, "tex27")
		glUniform1i(texLoc, 27)
		texLoc = glGetUniformLocation(program, "tex28")
		glUniform1i(texLoc, 28)
		texLoc = glGetUniformLocation(program, "tex29")
		glUniform1i(texLoc, 29)
		texLoc = glGetUniformLocation(program, "tex30")
		glUniform1i(texLoc, 30)
		texLoc = glGetUniformLocation(program, "tex31")
		glUniform1i(texLoc, 31)

		glActiveTexture(GL_TEXTURE31)
		glBindTexture(GL_TEXTURE_2D, offscreens[31].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER) 
		glActiveTexture(GL_TEXTURE30)
		glBindTexture(GL_TEXTURE_2D, offscreens[30].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)
		glActiveTexture(GL_TEXTURE29)
		glBindTexture(GL_TEXTURE_2D, offscreens[29].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)
		glActiveTexture(GL_TEXTURE28)
		glBindTexture(GL_TEXTURE_2D, offscreens[28].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER) 
		glActiveTexture(GL_TEXTURE27)
		glBindTexture(GL_TEXTURE_2D, offscreens[27].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER) 
		glActiveTexture(GL_TEXTURE26)
		glBindTexture(GL_TEXTURE_2D, offscreens[26].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER) 
		glActiveTexture(GL_TEXTURE25)
		glBindTexture(GL_TEXTURE_2D, offscreens[25].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER) 
		glActiveTexture(GL_TEXTURE24)
		glBindTexture(GL_TEXTURE_2D, offscreens[24].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER) 
		glActiveTexture(GL_TEXTURE23)
		glBindTexture(GL_TEXTURE_2D, offscreens[23].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)   	 
		glActiveTexture(GL_TEXTURE22)
		glBindTexture(GL_TEXTURE_2D, offscreens[22].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)   	 
		glActiveTexture(GL_TEXTURE21)
		glBindTexture(GL_TEXTURE_2D, offscreens[21].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)   	 
		glActiveTexture(GL_TEXTURE20)
		glBindTexture(GL_TEXTURE_2D, offscreens[20].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)   	 
		glActiveTexture(GL_TEXTURE19)
		glBindTexture(GL_TEXTURE_2D, offscreens[19].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)   	 
		glActiveTexture(GL_TEXTURE18)
		glBindTexture(GL_TEXTURE_2D, offscreens[18].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)   	 
		glActiveTexture(GL_TEXTURE17)
		glBindTexture(GL_TEXTURE_2D, offscreens[17].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)   	 
		glActiveTexture(GL_TEXTURE16)
		glBindTexture(GL_TEXTURE_2D, offscreens[16].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)
		glActiveTexture(GL_TEXTURE15)
		glBindTexture(GL_TEXTURE_2D, offscreens[15].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER) 
		glActiveTexture(GL_TEXTURE14)
		glBindTexture(GL_TEXTURE_2D, offscreens[14].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)
		glActiveTexture(GL_TEXTURE13)
		glBindTexture(GL_TEXTURE_2D, offscreens[13].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)
		glActiveTexture(GL_TEXTURE12)
		glBindTexture(GL_TEXTURE_2D, offscreens[12].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER) 
		glActiveTexture(GL_TEXTURE11)
		glBindTexture(GL_TEXTURE_2D, offscreens[11].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER) 
		glActiveTexture(GL_TEXTURE10)
		glBindTexture(GL_TEXTURE_2D, offscreens[10].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER) 
		glActiveTexture(GL_TEXTURE9)
		glBindTexture(GL_TEXTURE_2D, offscreens[9].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER) 
		glActiveTexture(GL_TEXTURE8)
		glBindTexture(GL_TEXTURE_2D, offscreens[8].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER) 
		glActiveTexture(GL_TEXTURE7)
		glBindTexture(GL_TEXTURE_2D, offscreens[7].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)   	 
		glActiveTexture(GL_TEXTURE6)
		glBindTexture(GL_TEXTURE_2D, offscreens[6].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)   	 
		glActiveTexture(GL_TEXTURE5)
		glBindTexture(GL_TEXTURE_2D, offscreens[5].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)   	 
		glActiveTexture(GL_TEXTURE4)
		glBindTexture(GL_TEXTURE_2D, offscreens[4].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)   	 
		glActiveTexture(GL_TEXTURE3)
		glBindTexture(GL_TEXTURE_2D, offscreens[3].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)   	 
		glActiveTexture(GL_TEXTURE2)
		glBindTexture(GL_TEXTURE_2D, offscreens[2].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)   	 
		glActiveTexture(GL_TEXTURE1)
		glBindTexture(GL_TEXTURE_2D, offscreens[1].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)   	 
		glActiveTexture(GL_TEXTURE0)
		glBindTexture(GL_TEXTURE_2D, offscreens[0].color_texture)
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)   	
		
		
		texco = [(1, 1), (0, 1), (0, 0), (1, 0)]
		verco = [(1.0, 1.0), (-1.0, 1.0), (-1.0, -1.0), (1.0, -1.0)]

		glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

		glColor4f(1.0, 1.0, 1.0, 1.0)   	

		glBegin(GL_QUADS)
		for i in range(4):
			glTexCoord3f(texco[i][0], texco[i][1], 0.0)
			glVertex2f(verco[i][0], verco[i][1])
		glEnd() 	  

		# restoring settings
		glBindTexture(GL_TEXTURE_2D, act_tex[0])

		glDisable(GL_TEXTURE_2D)

		# reset view
		glMatrixMode(GL_PROJECTION)
		glPopMatrix()

		glMatrixMode(GL_MODELVIEW)
		glPopMatrix()

		glViewport(viewport[0], viewport[1], viewport[2], viewport[3])
		glScissor(viewport[0], viewport[1], viewport[2], viewport[3])
		glUseProgram(0)

	# operator functions
	@classmethod
	def poll(cls, context):
		''' Limit the operator to the area type specified '''
		return context.area.type == 'IMAGE_EDITOR'

	def modal(self, context, event):
		if context.area:
			context.area.tag_redraw()

		return {'PASS_THROUGH'}

	def invoke(self, context, event):
		if OffScreenDraw.is_enabled:
			self.cancel(context)

			return {'FINISHED'}

		else:
			OffScreenDraw.handle_add(self, context)
			OffScreenDraw.is_enabled = True

			if context.area:
				# store the editor window from where the operator whas invoked
				context.area.tag_redraw()
			
			scn = context.scene
			# get the global properties from window manager
			wm = context.window_manager	
			#some parameters for the shader need to be computed once
			self.newPitch = wm.pitch * (wm.screenW / wm.DPI) * cos(atan(1 / wm.slope))
			self.newTilt = wm.screenH / (wm.screenW * wm.slope)
			self.subPixelSize = 1 / (wm.screenW * 3)
			if wm.flipSubp == 0:
				self.redIndex = 0
				self.blueIndex = 2
			else:
				self.redIndex = 2
				self.blueIndex = 0
			#self.redIndex = (self.flipSubp == 0 ? 0 : 2)
			#self.blueIndex = (self.flipSubp == 0 ? 2 : 0)
			
			# compile shaders
			create_shader_program()

			# the focal distance of the active camera is used as focal plane
			# thus it should not be 0 because then the system won't work
			cam = context.scene.camera
			if cam.data.dof_distance == 0.0:
				# using distance of the camera to the center of the scene as educated guess
				# for the initial distance of the focal plane
				cam.data.dof_distance = cam.location.magnitude

			# change the render aspect ratio so the view in the looking glass does not get deformed
			aspect_ratio = wm.screenW / wm.screenH
			context.scene.render.resolution_x = context.scene.render.resolution_y * aspect_ratio

			context.window_manager.modal_handler_add(self)
			return {'RUNNING_MODAL'}

	def cancel(self, context):
		OffScreenDraw.handle_remove()
		OffScreenDraw.is_enabled = False

		if context.area:
			context.area.tag_redraw()

# ------------ UI Functions -------------
class looking_glass_window_setup(bpy.types.Operator):
	""" Creates a new window of type image editor """
	bl_idname = "lookingglass.window_setup"
	bl_label = "Create Window"
	bl_description = "Creates a new window of type image editor that can be used in the looking glass display."
	bl_options = {'REGISTER', 'UNDO'}

	@staticmethod
	def load_calibration():
		user_preferences = bpy.context.user_preferences
		filepath = user_preferences.addons["looking_glass_tools"].preferences.filepath
		print(filepath)
		try:
			config_json_raw = subprocess.run([filepath], stdout=subprocess.PIPE)
			config_json_text = config_json_raw.stdout.decode('UTF-8')
			config_json = json.loads(config_json_text)
			print("Loading of config success, center: " + str(config_json['center']['value']))
			wm = bpy.context.window_manager
			wm.pitch = float(config_json['pitch']['value'])
			wm.slope = float(config_json['slope']['value'])
			wm.center = float(config_json['center']['value'])
			wm.invView = float(config_json['invView']['value'])
			wm.DPI = float(config_json['DPI']['value'])
			wm.screenW = float(config_json['screenW']['value'])
			wm.screenH = float(config_json['screenH']['value'])
			wm.flipImageX = float(config_json['flipImageX']['value'])
			wm.flipImageY = float(config_json['flipImageY']['value'])
			wm.flipSubp = float(config_json['flipSubp']['value'])

		except:
			print("Loading of config failed. Check file path of config utility in the addon preferences.")



	def execute(self, context):
		# Call user prefs window
		bpy.ops.screen.area_dupli('INVOKE_DEFAULT')

		# Change area type
		area = bpy.context.window_manager.windows[-1].screen.areas[0]
		area.type = 'IMAGE_EDITOR'
		OffScreenDraw.area = area
		self.load_calibration()
		print("Loaded Calibration")
		return {'FINISHED'}

def menu_func(self, context):
	''' Helper function to add the operator to menus '''
	print("appended the menu function")
	self.layout.operator(OffScreenDraw.bl_idname)

def register():
	bpy.utils.register_class(OffScreenDraw)
	bpy.utils.register_class(looking_glass_window_setup)
	bpy.types.IMAGE_MT_view.append(menu_func)
	print("registered the live view")

def unregister():
	bpy.utils.unregister_class(looking_glass_window_setup)
	bpy.utils.register_class(OffScreenDraw)
	bpy.types.IMAGE_MT_view.remove(menu_func)

if __name__ == "__main__":
	register()