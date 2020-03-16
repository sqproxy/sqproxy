import click


@click.group()
def sqproxy():
    """Basic entrypoint"""


@sqproxy.command()
def run():
    """Run SQProxy process"""
    from .__main__ import run

    run()


if __name__ == '__main__':
    sqproxy()
