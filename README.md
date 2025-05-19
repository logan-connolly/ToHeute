# toheute

> a simple utility for copying in local changes to checkmk sites.

## setup

The `toheute.py` is a self-contained python script that can be run by [uv](https://github.com/astral-sh/uv). Since it is an executable, you just need to make sure that the executable can be found on your path. For example:

```console
ln -sf $PWD/toheute.py $HOME/.local/bin/toheute.py
```

Once it's there, simply run the following command from a checkmk repository:

```console
toheute.py
```

You will then be presented with a dialog for which site to patch your change to.

### options

Run `toheute.py --help` to see what options are available:

```console
Usage: toheute.py [OPTIONS]

  Patch your local HEAD commit into a running Checkmk site.

Options:
  --no-reload    Don't reload services.
  --full-reload  Force a full reload of services.
  --help         Show this message and exit.
```

## development

To create a dedicated virtual environment with required dependencies, run:

```console
uv venv --python 3.12
uv pip install gitpython rich
source .venv/bin/activate[.fish]
```

## disclaimer

This is not an all inclusive tool for checkmk development, but instead a simple one that meets most use cases.

## acknowledgments

The original [implementation](https://github.com/gavinmcguigan/ToHeute) was created by [@gavinmcguigan](https://github.com/gavinmcguigan) - all props should be directed his way.
