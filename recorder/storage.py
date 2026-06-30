import boto3

def s3_key(device_id, when, uuid) -> str:
    return f"{device_id}/{when:%Y}/{when:%m}/{when:%Y%m%dT%H%M%S}-{uuid}.mp3"

class Storage:
    def __init__(self, config, s3_client=None):
        self.bucket, self.ttl = config.s3_bucket, config.presign_ttl
        self._s3 = s3_client or boto3.client(
            "s3", region_name=config.aws_region,
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key)

    def put(self, local_path, key, metadata):
        self._s3.upload_file(local_path, self.bucket, key, ExtraArgs={
            "Metadata": {k: str(v) for k, v in metadata.items()}, "ContentType": "audio/mpeg"})

    def presign_get(self, key):
        return self._s3.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=self.ttl)
