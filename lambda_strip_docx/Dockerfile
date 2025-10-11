FROM public.ecr.aws/lambda/python:3.13@sha256:eb6f5fd5d8904084bc7d7d60b5714a0d3d0a751e570f7ba9869de9e46cf5ec68

# Install dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt --target "/var/task"

# Copy function code
COPY . /var/task/

# Set the CMD to your handler (handler.lambda_handler)
CMD ["lambda_function.lambda_handler"]
