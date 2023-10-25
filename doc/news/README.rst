Recording Changes
=================
 
This directory contains "news fragments" which are small, structured text files that contain information about changes or updates that will be included in the release notes. 
These fragments are used to automatically generate changelogs or release notes.
They can be written restructured text format or plain text.

Each file should be named like ``<JIRA TICKET>.<TYPE>.<EXT>`` with a file extension defining the markup format (``rst|md``).
The ``<TYPE>`` should be one of:

* ``feature``: A new feature
* ``bugfix``: A bug fix.
* ``perf``: A performance enhancement.
* ``doc``: A documentation improvement.
* ``removal``: A deprecation or removal of API.
* ``misc``: Other minor changes and/or additions

An example file name would therefore look like ``DM-40534.doc.rst``.

Each developer now has to create the news fragments for the changes they have made on their own branches, 
instead of adding them to the release notes directly.
The news fragments are then automatically integrated into the release notes by the ``towncrier`` tool.

You can test how the content will be integrated into the release notes by running ``towncrier build --draft --version=v<X.XX.X>``. 
Note that you have to run it from the root repository directory (i.e. the ``ts_observatory_control``).

In order to update the release notes file for real, the person responsible for the release should run:

.. code-block:: bash

   $ towncrier build --version=v<X.XX.X>


.. note::

   When running towncrier to build the changelog, you may be prompted to confirm the deletion of fragments. 
   If you would like to retain the fragments in the doc/news directory do not confirm the deletion.
   
Note also that ``towncrier`` can be installed from PyPI or conda-forge. 
