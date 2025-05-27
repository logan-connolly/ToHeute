# toheute

> sync local changes with a Checkmk site.

## setup

`toheute.py` is a self-contained python script that requires
[uv](https://github.com/astral-sh/uv) to run.

The script can be run as an executable, so you only need to make sure that it
can be found on your path:

```console
ln -sf $PWD/toheute.py $HOME/.local/bin/toheute.py
```

Once it's there, navigate to the checkmk repository and run:

```console
toheute.py
```

### options

Run `toheute.py --help` to see what options are available:

```console
Usage: toheute.py [OPTIONS]

  Patch your local HEAD commit into a running Checkmk site.

Options:
  --n-commits INTEGER  Number of commits to sync.
  --no-reload          Don't reload services.
  --full-reload        Force a full reload of services.
  --help               Show this message and exit.
```

## development

To create a dedicated virtual environment with required dependencies, run:

```console
uv venv --python 3.12
uv pip install click gitpython rich
source .venv/bin/activate
```

## disclaimer

This is not an all inclusive tool for checkmk development, but instead a simple
one that meets most use cases.

## acknowledgments

The original [implementation](https://github.com/gavinmcguigan/ToHeute) was
created by [@gavinmcguigan](https://github.com/gavinmcguigan) - all props
should be directed his way.
