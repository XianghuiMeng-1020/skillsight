import ProfileClient from './ProfileClient';

export function generateStaticParams() {
  return [{ userId: '_' }];
}

export default function PublicProfilePage() {
  return <ProfileClient />;
}
