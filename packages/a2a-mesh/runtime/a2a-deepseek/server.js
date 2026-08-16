#!/usr/bin/env node
import 'dotenv/config';
import { startExternalAgentServer } from '../a2a-shared/external-agent-server.js';
await startExternalAgentServer('deepseek');
