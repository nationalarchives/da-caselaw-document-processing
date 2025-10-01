FROM public.ecr.aws/lambda/python:3.13@sha256:d9edaacb31059fc0ac2a98849ef5c271df0a81be36e8d78dfb72a414483f2e0a

# Install dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt --target "/var/task"

# Copy function code
COPY . /var/task/

# Set the CMD to your handler (handler.lambda_handler)
CMD ["lambda_function.lambda_handler"]
