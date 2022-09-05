from . import ecs

import pyglet


class RenderSystem(ecs.System):

    def update(self):
        window_entity = list(ecs.Entity.with_component("window"))[0]
        window = window_entity['window']
        camera = window.camera_position
        viewport = window.viewport_size
        width, height = window.window.width, window.window.height

        layer_paralax = [10, 8, 2]
        for paralax, sprite in zip(layer_paralax, window.background_layers):

            sl = int(camera.x // paralax) - width // 2
            sr = int(camera.x // paralax + width) - width // 2
            st = int(camera.y // paralax + height) - height // 2
            sb = int(camera.y // paralax) - height // 2

            ixl = int(sl // sprite.width)
            ixr = int(sr // sprite.width)
            ixt = int(st // sprite.height)
            ixb = int(sb // sprite.height)

            for ox in range(ixl, ixr + 1):
                for oy in range(ixb, ixt + 1):
                    sprite.x = width // 2 - camera.x // paralax + ox * sprite.width
                    sprite.y = height // 2 - camera.y // paralax + oy * sprite.height
                    sprite.draw()


        ox = width // 2 - camera.x
        oy = height // 2 - camera.y

        entities = ecs.Entity.with_component("emitter")
        for entity in entities:
            emitter = entity['emitter']
            for sprite in emitter.sprites:
                sprite.x += ox
                sprite.y += oy
            emitter.batch.draw()
            for sprite in emitter.sprites:
                sprite.x -= ox
                sprite.y -= oy

        entities = ecs.Entity.with_component("flight path")
        for entity in entities:
            flight_path = entity["flight path"]
            pyglet.gl.glEnable(pyglet.gl.GL_LINE_SMOOTH)
            pyglet.gl.glHint(pyglet.gl.GL_LINE_SMOOTH_HINT, pyglet.gl.GL_NICEST)
            pyglet.gl.glMatrixMode(pyglet.gl.GL_MODELVIEW)
            pyglet.gl.glTranslatef(ox, oy, 0.0)
            flight_path.vertices.draw(pyglet.gl.GL_LINE_STRIP)
            pyglet.gl.glLoadIdentity()

        entities = ecs.Entity.with_component("sprite")
        for entity in entities:
            physics = entity['physics']
            if physics is None:
                continue
            sprite = entity['sprite']
            sprite.x = physics.position.x + ox
            sprite.y = physics.position.y + oy
            sprite.rotation = float(-physics.rotation)
            sprite.draw()

