FROM public.ecr.aws/lambda/python:3.13@sha256:a0ca8c190db48ddbb341ce893f4a4ecf04b1adf9b696e0b26066c29211e4cdff

# Install dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt --target "/var/task"

# Copy function code
COPY . /var/task/

# Set the CMD to your handler (handler.lambda_handler)
CMD ["lambda_function.lambda_handler"]
