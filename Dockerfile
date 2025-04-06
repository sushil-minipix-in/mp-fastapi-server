FROM python:3.8-slim

ARG USERNAME=container-user
ARG USER_UID=1000
ARG USER_GID=1000

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME

USER $USERNAME
ENV PATH=$PATH:/home/$USERNAME/.local/bin
RUN mkdir -p /home/$USERNAME/app
WORKDIR /home/$USERNAME/app

COPY pyproject.toml .

RUN pip install poetry==1.5.1
RUN poetry config virtualenvs.create false
RUN poetry install --no-dev

COPY app/ app/
COPY jobs/ jobs/

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--workers", "4"]
