# Data formats

## Standards Metadata

The files in the data directory are read by the scripts in the tools directory and contain the data with which the content space for the standard documents is created.

There is one file in the data directory for each standard. The file names represent the short names of the standards. The actual fully qualified name of the standard is specified as the name metadata variable in the header area of the file.

The core element for defining the content space for the respective standard are the character strings in the structure array. The structure of the table of contents is mapped here as a numerical index for each volume of a standard. The different standards follow their own internal structure models. IEC 61508:2005 consists of 8 volumes, starting with 0. ISO 26262:2018 consists of 12 volumes, starting with 1. The Cenelec standards EN 50126/8/9 and EN 50657 are each independent with only one volume, but all belong together in terms of content to the topic of functional safety.

These different structures are configured for uniform treatment in the standards atlas using the metadata in the header of the respective data files. The volumes in IEC 61508 are shifted upwards by one for representation in numerical UIDs. In ISO 26262, two digits are reserved in the UID for the representation of the volumes. Depending on the depth of the index nesting, more or fewer numerical digits are used for the UID.

The actual structure is then created using the character strings in the structures array. There is one such character string for each volume. Each element of a standard document to be identified for the purpose of content referencing is represented here with an index number. The syntax is as follows

'''
[volume-][type][enum:]index[.{range}]
'''

For standards with several volumes, the volume number is specified as the first number and separated from the rest of the item with a minus sign.

The index can be preceded by a type classification. The following types are currently recognized:

* *r* Requirement
* *s* Scope
* *t* Term
* *o* Objective
* *c* Clause

All other index entries are simply the table of content.

If the TOC entry in the standard begins with a capital letter (typical for the annexes), the index is preceded by a number to assign this index to the numerical system of UIDs and separated from the index by a colon.

Finally, the index can also contain enumerations to simplify areas with continuous numbering.

## Standards default content

The remaining lines in the data file are used to initialize the items when they are created by doorstop. In particular, the headings for the table of contents or the title lines for the display of the individual items can be defined here. It is also possible to initialize the text entries for the items when they are created.

The data is stored as a semicolon separated list.

The lines marked as TOC in the first column are used for the table of contents or the title lines, and those marked as TEXT are used for the text.

The second column contains an md5 hash to uniquely identify each entry.

The third column contains either the doorstop UID of the item or the complete index reference in the standard document.

The fourth column then contains the actual character string defined to initialize the respective item.

## Mappings

The actual purpose of the standards atlas is to establish and discuss relationships between the individual elements of the various standards.

In doorstop there is only a single-directional link relationship. To persist this relationship in the standards atlas, the mapping files are stored in the data directory.

Essentially, these are again lists with semicolon separated values. The UIDs of the standards to be linked are listed in the first and fourth columns. Text snippets may be included in between for better traceability. However, these are irrelevant for automatic processing.

All mappings files are read by linkItems and the corresponding connections are created.
