import json
import boto3
import os
import math

import nltk
from nltk.tokenize import word_tokenize
from nltk.tokenize.treebank import TreebankWordDetokenizer

nltk.data.path.append("/tmp")
nltk.download("punkt", download_dir="/tmp")

S3_BUCKET = os.environ.get('S3_BUCKET')
SOURCE_PREFIX = os.environ.get('SOURCE_PREFIX')
DESTINATION_PREFIX = os.environ.get('DESTINATION_PREFIX')
ENDPOINT_NAME = os.environ.get('SAGEMAKER_ENDPOINT_NAME')

CHUNK_LENGTH = 400

s3_client = boto3.client('s3')


def lambda_handler(event, context):
    print(event)

    # Load transcript
    transcript_key = event['Records'][0]['s3']['object']['key']
    tokens = transcript_key.split('/')[1].split('.')

    transcript_name = tokens[0]
    file_format = tokens[1]
    source_uri = 's3://{}/{}'.format(S3_BUCKET, transcript_key)
    output_key = '{}/{}.txt'.format(DESTINATION_PREFIX, transcript_name)

    s3_client.download_file(Bucket=S3_BUCKET, Key=transcript_key, Filename='/tmp/transcript.txt')
    with open('/tmp/transcript.txt') as f:
        contents = json.load(f)

    # Chunk transcript into chunks
    transcript = contents['results']['transcripts'][0]['transcript']
    transcript_tokens = word_tokenize(transcript)

    num_chunks = int(math.ceil(len(transcript_tokens) / CHUNK_LENGTH))
    transcript_chunks = []
    for i in range(num_chunks):
        if i == num_chunks - 1:
            chunk = TreebankWordDetokenizer().detokenize(transcript_tokens[CHUNK_LENGTH * i:])
        else:
            chunk = TreebankWordDetokenizer().detokenize(transcript_tokens[CHUNK_LENGTH * i:CHUNK_LENGTH * (i + 1)])
        transcript_chunks.append(chunk)

    print('Transcript broken into {} chunks of {} tokens.'.format(len(transcript_chunks), CHUNK_LENGTH))

    # Invoke endpoint with transcript and instructions
    instruction = 'Summarize the context above.'

    try:
        # Summarize each chunk
        chunk_summaries = []
        for i in range(len(transcript_chunks)):
            text_input = '{}\n{}'.format(transcript_chunks[i], instruction)

            payload = {
                "text_inputs": text_input,
                "max_length": 100,
                "num_return_sequences": 1,
                "top_k": 50,
                "top_p": 0.95,
                "do_sample": True
            }
            query_response = query_endpoint_with_json_payload(json.dumps(payload).encode('utf-8'))
            generated_texts = parse_response_multiple_texts(query_response)
            chunk_summaries.append(generated_texts[0])

        # Create a combined summary
        text_input = '{}\n{}'.format(' '.join(chunk_summaries), instruction)
        payload = {
            "text_inputs": text_input,
            "max_length": 100,
            "num_return_sequences": 1,
            "top_k": 50,
            "top_p": 0.95,
            "do_sample": True
        }
        query_response = query_endpoint_with_json_payload(json.dumps(payload).encode('utf-8'))
        generated_texts = parse_response_multiple_texts(query_response)

        results = {
            "summary": generated_texts,
            "chunk_summaries": chunk_summaries
        }

    except Exception as e:
        print('Error generating text')
        print(e)
        raise

    # Save response to S3
    with open('/tmp/output.txt', 'w') as f:
        json.dump(results, f)

    s3_client.put_object(Bucket=S3_BUCKET, Key='{}/{}.txt'.format(DESTINATION_PREFIX, transcript_name),
                         Body=open('/tmp/output.txt', 'rb'))

    # Return response
    return {
        'statusCode': 200,
        'body': {
            'message': json.dumps('Completed summary job {}'.format(transcript_name)),
            'results': results
        }
    }


def query_endpoint(encoded_text):
    client = boto3.client('runtime.sagemaker')
    response = client.invoke_endpoint(EndpointName=ENDPOINT_NAME, ContentType='application/x-text', Body=encoded_text)
    return response


def parse_response(query_response):
    model_predictions = json.loads(query_response['Body'].read())
    generated_text = model_predictions['generated_text']
    return generated_text


def query_endpoint_with_json_payload(encoded_json):
    client = boto3.client('runtime.sagemaker')
    response = client.invoke_endpoint(EndpointName=ENDPOINT_NAME, ContentType='application/json', Body=encoded_json)
    return response


def parse_response_multiple_texts(query_response):
    model_predictions = json.loads(query_response['Body'].read())
    generated_text = model_predictions['generated_texts']
    return generated_text