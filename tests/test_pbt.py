"""
TODO

What I wanted to do here was to use the meta-schemas from
https://json-schema.org/specification.html i.e. the JSON Schema that descibes
valid JSON Schemas, to generate schemas to test my fakers with.

I thought I could use hypothesis-jsonschema to do this but unfortunately the
meta-schema is too large and has recursive elements which are not well handled.

I could use my own faker, but it seems like it would be better to have an
independent oracle. In the in this might not be a bad idea though... it would
allow to test a round-trip:
    - generate a schema from the meta-schema
    - validate the schema against the meta-schema
    - generate data from the schema
    - validate generated data against the schema

There is a risk that some bug in the faker prevents whole classes of schema to
be generated of course. Probably worthwhile since easy.

Maybe we can still try and test smaller fragments via hypothesis-jsonschema?

Maybe an alternative oracle?  Though that has the same problem.
Here is one:
https://github.com/json-schema-faker/json-schema-faker/blob/master/docs/USAGE.md

One thing they appear to do is test generated schemas against multiple
validation libs:
https://github.com/json-schema-faker/json-schema-faker/blob/master/tests/schema/validator.js
Otherwise just comprehensive tests of various schema features:
https://github.com/json-schema-faker/json-schema-faker/tree/master/tests/schema/core

How do we compare feature-wise?
"""
