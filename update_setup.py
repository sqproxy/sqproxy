"""
Замена оригинальной команде `dephell convert deps`
тк иногда с ней бывают проблемы и она падает с TypeError
"""
import pathlib

from dephell import converters
from dephell.controllers import Graph
from dephell.models import Requirement

BASEDIR = pathlib.Path(__file__).parent

if __name__ == '__main__':
    pc = converters.PoetryConverter()
    spc = converters.SetupPyConverter()

    root = pc.load(BASEDIR.joinpath('pyproject.toml'))
    if root.readme.markup == 'md':
        # SetupPyConverter принудительно конвертирует README в rst
        # чтобы этого не допустить - обманываем его
        root.readme.markup = 'rst'

    reqs = Requirement.from_graph(graph=Graph(root), lock=False)
    content = spc.dumps(reqs, project=root)

    BASEDIR.joinpath('setup.py').write_text(content)

    print('setup.py was updated successfully')
