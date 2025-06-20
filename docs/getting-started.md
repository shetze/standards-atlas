In order to get started, you need python3 and python3-venv as prerequisite.
Afterwards you can run the following command in order to install all necessary prerequisites and sets up the python venv:
```sh
$ source setup.sh
```


## Patch doorstop
The version 2.2.1 of doorstop as installed with pip lacks some fixes/features for use with standards-atlas.
To fix the local installation you can use the patch-doorstop.v2.2.1 script

```sh
$ ./tools/patch-doorstop.v2.2.1 ~/.local/lib/python3.12/site-packages/doorstop
```

## Getting started with standards-atlas

Next you probably want to clone this repo to work with it.

With a bit of further reading in the doorstop documentation, it becomes clear that the tool itself works a great deal with git. To avoid nested git repositories, the content generated by the Standards Atlas should be kept in a separate directory from the Standards Atlas. This can be, for example, a project in which the standards are to be used as a reference for the specific requirements.

The main tool is located under tools/standards-atlas.
To get started you can just run it with the following command:
```sh
$ ./tools/standards-atlas
```
This will create the whole standards-atlas doorstop files under **/tmp/standards-atlas**
You can change this by running the script with the parameter **"-d"**

Usage:
```sh
$ ./tools/standards-atlas --help
```

## Automatic publishing
In order to automatically publish the created doorstop files and have them usable as html files, you can activate automatic publishing with the following parameter:
```sh
$ ./tools/standards-atlas -t
```
## Automatic referencing of travelogues
In order to automatically reference doorstop items to travelogue files, you can activate automatic referencing with the following parameter:
```sh
$ ./tools/standards-atlas -l
```

## No recreation
In order to not recreate the files (e.g. if you just want to update your references and publish) you can deactivate recreation with the following parameter
```sh
$ ./tools/standards-atlas -n
```

## Next steps

Once you have created and published the initial set of doorstop files you can load the local index file with your browser. This will allow you to browse through the standards structure.

This structure is without content, simply because the actual standard documents are protected by copyright and may not be reproduced here in thes git repo.

However, you have the structure and this does allow you to comment on all the clauses in a reproducable and publicly shareable way. Not much, but better than nothing. The documents in the travelogue directory sowh how to use this feature.

If you have the actual standard documents at hand, you may be able to use the structural information provided by the standards-atlas to process the information from the standard documents in one way or another. So this is definitely a starting point for local use cases. You can use the atlaslocaldir to include additional data into the doorstop generation process.

TBC

