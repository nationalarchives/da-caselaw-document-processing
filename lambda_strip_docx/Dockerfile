FROM public.ecr.aws/lambda/python:3.13@sha256:3d3dd33b9dc91232af3736475fb593f9e3e51efe614730f7f7658d70259889f2

# Install dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt --target "/var/task"

# Copy function code
COPY . /var/task/

# Set the CMD to your handler (handler.lambda_handler)
CMD ["lambda_function.lambda_handler"]
