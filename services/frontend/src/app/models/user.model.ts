// src/app/models/user.model.ts
export interface IdToken {
    name: string;
    given_name: string;
    family_name: string;
    preferred_username: string;
    email: string;
    email_verified: boolean;
}

export interface UserProfileResponse {
    id_token: IdToken;
}