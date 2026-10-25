-- The roles and databases scripts/dev.py creates for the dev container, for a container that is empty on every run.
CREATE ROLE agent LOGIN PASSWORD 'change-me';
CREATE DATABASE agent OWNER agent;
CREATE ROLE teams LOGIN PASSWORD 'change-me';
CREATE DATABASE teams OWNER teams;
CREATE ROLE polymarket LOGIN PASSWORD 'change-me';
CREATE DATABASE polymarket OWNER polymarket;
CREATE ROLE social LOGIN PASSWORD 'change-me';
CREATE DATABASE social OWNER social;
CREATE ROLE telegram LOGIN PASSWORD 'change-me';
CREATE DATABASE telegram OWNER telegram;
CREATE ROLE strategies LOGIN PASSWORD 'change-me';
CREATE DATABASE strategies OWNER strategies;
