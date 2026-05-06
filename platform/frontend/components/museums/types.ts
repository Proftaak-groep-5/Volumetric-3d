import User from "@/components/users/types";

export default interface Museum {
    id: number;
    name: string;
    owner: User;
    description: string;
}