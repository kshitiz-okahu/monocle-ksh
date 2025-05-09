from monocle_apptrace.instrumentation.metamodel.langchain import (
    _helper,
)

RETRIEVAL = {
    "type": "retrieval",
    "attributes": [
        [
            {
                "_comment": "vector store name and type",
                "attribute": "name",
                "accessor": lambda arguments: type(arguments['instance'].vectorstore).__name__
            },
            {
                "attribute": "type",
                "accessor": lambda arguments: 'vectorstore.' + type(arguments['instance'].vectorstore).__name__
            },
            {
                "attribute": "deployment",
                "accessor": lambda arguments: _helper.extract_vectorstore_deployment(
                    arguments['instance'].vectorstore.__dict__)
            }
        ],
        [
            {
                "_comment": "embedding model name and type",
                "attribute": "name",
                "accessor": lambda arguments: _helper.resolve_from_alias(arguments['instance'].vectorstore.embeddings.__dict__,['endpoint_name','model_id','model'])
            },
            {
                "attribute": "type",
                "accessor": lambda arguments: 'model.embedding.' + _helper.resolve_from_alias(arguments['instance'].vectorstore.embeddings.__dict__,['endpoint_name','model_id','model'])
            }
        ]
    ],
    "events": [
        {"name": "data.input",
         "attributes": [

             {
                 "_comment": "this is instruction and user query to LLM",
                 "attribute": "input",
                 "accessor": lambda arguments: _helper.update_input_span_events(arguments['args'])
             }
         ]
         },
        {
            "name": "data.output",
            "attributes": [
                {
                    "_comment": "this is result from LLM",
                    "attribute": "response",
                    "accessor": lambda arguments: _helper.update_output_span_events(arguments['result'])
                }
            ]
        }
    ]
}
