import * as AWS from "aws-sdk";

export type DoorStatus = 'open' | 'closed'

export interface VisitorRequest {
    phoneNumber: string
    passcode: number
    status: DoorStatus
}

export interface DoorResponse {
    status: DoorStatus
    pending?: number
    name?: string
    error?: string
}

export type PartialUnknown<T> = T extends object ? {
    [P in keyof T]: unknown
} : unknown;

export const passcodeTableName = 'passcodes';
export interface PasscodeTableEntry {
    phoneNumber: string
    passcode: number
    ttl: number
}

export const visitorTableName = 'visitors';
export const visitorPhoneNumberIndexName = 'phoneNumber-index';
export interface VisitorTableEntry {
    faceId: string
    imageId: string
    name: string
    phoneNumber: string
}

export const awsConfig: Parameters<typeof AWS.config.update>[0] = { region: 'us-east-1' };
